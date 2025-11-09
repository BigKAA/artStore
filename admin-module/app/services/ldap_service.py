"""
LDAP Service для интеграции с корпоративным LDAP/AD.
Поддерживает аутентификацию и синхронизацию пользователей.
"""

from typing import Optional, Dict, List
import logging

from ldap3 import Server, Connection, ALL, SIMPLE, SUBTREE
from ldap3.core.exceptions import LDAPException, LDAPBindError

from app.core.config import settings
from app.models.user import UserRole

logger = logging.getLogger(__name__)


class LDAPService:
    """
    Сервис для работы с LDAP/Active Directory.

    Функции:
    - Аутентификация пользователей через LDAP
    - Получение информации о пользователе
    - Mapping LDAP групп на роли
    - Синхронизация пользователей
    """

    def __init__(self):
        """Инициализация LDAP сервиса."""
        if not settings.ldap.enabled:
            logger.info("LDAP is disabled")
            return

        try:
            # Создаем LDAP сервер
            self.server = Server(
                settings.ldap.server,
                get_info=ALL
            )
            logger.info(f"LDAP server configured: {settings.ldap.server}")

        except Exception as e:
            logger.error(f"Failed to configure LDAP server: {e}")
            raise

    def _get_admin_connection(self) -> Optional[Connection]:
        """
        Создание административного подключения к LDAP.

        Returns:
            Optional[Connection]: LDAP connection или None при ошибке
        """
        if not settings.ldap.enabled:
            return None

        try:
            conn = Connection(
                self.server,
                user=settings.ldap.bind_dn,
                password=settings.ldap.bind_password,
                authentication=SIMPLE,
                auto_bind=True
            )
            return conn

        except LDAPBindError as e:
            logger.error(f"LDAP admin bind failed: {e}")
            return None

        except LDAPException as e:
            logger.error(f"LDAP connection error: {e}")
            return None

    def _map_groups_to_role(self, groups: List[str]) -> UserRole:
        """
        Mapping LDAP групп на роли пользователя.

        Args:
            groups: Список DN групп LDAP

        Returns:
            UserRole: Роль пользователя
        """
        # Проверяем маппинг из конфигурации
        for group_dn in groups:
            for group_pattern, role_name in settings.ldap.group_role_mapping.items():
                if group_pattern.lower() in group_dn.lower():
                    try:
                        return UserRole[role_name.upper()]
                    except KeyError:
                        logger.warning(f"Invalid role in mapping: {role_name}")

        # По умолчанию - обычный пользователь
        return UserRole.USER

    async def authenticate(self, username: str, password: str) -> Optional[Dict]:
        """
        Аутентификация пользователя через LDAP.

        Args:
            username: Имя пользователя LDAP
            password: Пароль

        Returns:
            Optional[Dict]: Данные пользователя если аутентификация успешна, None иначе
                {
                    "username": str,
                    "email": str,
                    "first_name": str,
                    "last_name": str,
                    "dn": str,
                    "role": UserRole,
                    "groups": List[str]
                }
        """
        if not settings.ldap.enabled:
            logger.warning("LDAP authentication attempted but LDAP is disabled")
            return None

        # Получаем информацию о пользователе через admin connection
        user_dn = await self._find_user_dn(username)
        if not user_dn:
            logger.warning(f"User not found in LDAP: {username}")
            return None

        # Проверяем пароль пользователя
        try:
            # Создаем connection с учетными данными пользователя
            user_conn = Connection(
                self.server,
                user=user_dn,
                password=password,
                authentication=SIMPLE,
                auto_bind=True
            )

            # Если дошли сюда - аутентификация успешна
            user_conn.unbind()

        except LDAPBindError:
            logger.warning(f"Invalid password for LDAP user: {username}")
            return None

        except LDAPException as e:
            logger.error(f"LDAP authentication error: {e}")
            return None

        # Получаем полную информацию о пользователе
        user_data = await self._get_user_info(user_dn)
        return user_data

    async def _find_user_dn(self, username: str) -> Optional[str]:
        """
        Поиск DN пользователя по username.

        Args:
            username: Имя пользователя

        Returns:
            Optional[str]: DN пользователя или None
        """
        conn = self._get_admin_connection()
        if not conn:
            return None

        try:
            # Поиск пользователя
            search_filter = f"(&(objectClass={settings.ldap.user_object_class})({settings.ldap.username_attribute}={username}))"

            conn.search(
                search_base=settings.ldap.user_search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=[settings.ldap.username_attribute]
            )

            if not conn.entries:
                return None

            # Возвращаем DN первого найденного пользователя
            user_dn = conn.entries[0].entry_dn
            conn.unbind()
            return user_dn

        except LDAPException as e:
            logger.error(f"LDAP search error: {e}")
            if conn:
                conn.unbind()
            return None

    async def _get_user_info(self, user_dn: str) -> Optional[Dict]:
        """
        Получение информации о пользователе по DN.

        Args:
            user_dn: Distinguished Name пользователя

        Returns:
            Optional[Dict]: Данные пользователя или None
        """
        conn = self._get_admin_connection()
        if not conn:
            return None

        try:
            # Получаем атрибуты пользователя
            attributes = [
                settings.ldap.username_attribute,
                settings.ldap.email_attribute,
                settings.ldap.firstname_attribute,
                settings.ldap.lastname_attribute,
                settings.ldap.member_attribute,
            ]

            conn.search(
                search_base=user_dn,
                search_filter="(objectClass=*)",
                search_scope=SUBTREE,
                attributes=attributes
            )

            if not conn.entries:
                conn.unbind()
                return None

            entry = conn.entries[0]

            # Получаем группы пользователя
            groups = await self._get_user_groups(user_dn, conn)

            # Определяем роль на основе групп
            role = self._map_groups_to_role(groups)

            # Формируем данные пользователя
            user_data = {
                "username": str(getattr(entry, settings.ldap.username_attribute, "")),
                "email": str(getattr(entry, settings.ldap.email_attribute, "")),
                "first_name": str(getattr(entry, settings.ldap.firstname_attribute, "")),
                "last_name": str(getattr(entry, settings.ldap.lastname_attribute, "")),
                "dn": user_dn,
                "role": role,
                "groups": groups
            }

            conn.unbind()
            return user_data

        except LDAPException as e:
            logger.error(f"Failed to get user info: {e}")
            if conn:
                conn.unbind()
            return None

    async def _get_user_groups(self, user_dn: str, conn: Connection) -> List[str]:
        """
        Получение списка групп пользователя.

        Args:
            user_dn: DN пользователя
            conn: LDAP connection

        Returns:
            List[str]: Список DN групп
        """
        try:
            # Поиск групп где пользователь является членом
            search_filter = f"(&(objectClass={settings.ldap.group_object_class})({settings.ldap.member_attribute}={user_dn}))"

            conn.search(
                search_base=settings.ldap.group_search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=["cn"]
            )

            groups = [entry.entry_dn for entry in conn.entries]
            return groups

        except LDAPException as e:
            logger.error(f"Failed to get user groups: {e}")
            return []

    async def test_connection(self) -> bool:
        """
        Тестирование подключения к LDAP серверу.

        Returns:
            bool: True если подключение работает
        """
        if not settings.ldap.enabled:
            return False

        conn = self._get_admin_connection()
        if not conn:
            return False

        conn.unbind()
        return True


# Глобальный экземпляр сервиса (создается только если LDAP включен)
ldap_service = LDAPService() if settings.ldap.enabled else None
