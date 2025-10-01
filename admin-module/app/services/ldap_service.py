"""
Сервис для работы с LDAP.
Поддерживает аутентификацию, поиск пользователей и синхронизацию групп.
"""
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.core.exceptions import LDAPException, LDAPBindError
from typing import Optional, Dict, List, Tuple
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LDAPService:
    """
    Сервис для интеграции с LDAP.

    Основные функции:
    - Аутентификация пользователей
    - Поиск информации о пользователях
    - Получение групп пользователя
    - Проверка принадлежности к группам администраторов
    """

    def __init__(self):
        """Инициализация LDAP сервиса"""
        self.config = settings.auth.ldap

        if not self.config.enabled:
            logger.info("LDAP интеграция отключена")
            return

        # Создание LDAP сервера
        self.server = Server(
            self.config.server,
            get_info=ALL,
            use_ssl=self.config.use_ssl,
            connect_timeout=self.config.connection_timeout
        )

        logger.info(f"LDAP сервис инициализирован: {self.config.server}")

    def _get_admin_connection(self) -> Optional[Connection]:
        """
        Создает административное подключение к LDAP.
        Используется для поиска пользователей.

        Returns:
            Connection или None при ошибке
        """
        try:
            conn = Connection(
                self.server,
                user=self.config.bind_dn,
                password=self.config.bind_password,
                auto_bind=True
            )
            return conn
        except LDAPException as e:
            logger.error(f"Ошибка подключения к LDAP: {e}")
            return None

    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[Dict]]:
        """
        Аутентификация пользователя через LDAP.

        Args:
            username: Имя пользователя
            password: Пароль

        Returns:
            Tuple (успех, данные_пользователя)
            данные_пользователя содержит: username, email, full_name, is_admin, groups

        Example:
            >>> success, user_data = ldap_service.authenticate("john", "password123")
            >>> if success:
            >>>     print(f"Пользователь {user_data['username']} успешно аутентифицирован")
        """
        if not self.config.enabled:
            logger.warning("LDAP отключен, но была попытка аутентификации")
            return False, None

        # Шаг 1: Поиск пользователя в LDAP через административное подключение
        admin_conn = self._get_admin_connection()
        if not admin_conn:
            return False, None

        try:
            # Формируем фильтр поиска
            search_filter = self.config.user_search_filter.format(username=username)

            # Поиск пользователя
            admin_conn.search(
                search_base=self.config.base_dn,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['*']  # Получаем все атрибуты
            )

            if not admin_conn.entries:
                logger.warning(f"Пользователь {username} не найден в LDAP")
                return False, None

            # Получаем DN (Distinguished Name) пользователя
            user_entry = admin_conn.entries[0]
            user_dn = user_entry.entry_dn

            logger.info(f"Найден пользователь в LDAP: {user_dn}")

        except LDAPException as e:
            logger.error(f"Ошибка поиска пользователя в LDAP: {e}")
            return False, None
        finally:
            admin_conn.unbind()

        # Шаг 2: Попытка bind с учетными данными пользователя
        try:
            user_conn = Connection(
                self.server,
                user=user_dn,
                password=password,
                auto_bind=True
            )

            logger.info(f"Успешная аутентификация пользователя {username} через LDAP")

            # Шаг 3: Получение данных пользователя
            user_data = self._extract_user_data(user_entry)

            # Шаг 4: Получение групп пользователя
            groups = self._get_user_groups(user_dn, user_conn)
            user_data['groups'] = groups

            # Шаг 5: Проверка является ли администратором
            user_data['is_admin'] = self._is_admin_user(groups)

            user_conn.unbind()

            return True, user_data

        except LDAPBindError as e:
            logger.warning(f"Неверные учетные данные для пользователя {username}: {e}")
            return False, None
        except LDAPException as e:
            logger.error(f"Ошибка LDAP при аутентификации: {e}")
            return False, None

    def _extract_user_data(self, ldap_entry) -> Dict:
        """
        Извлекает данные пользователя из LDAP entry.

        Args:
            ldap_entry: Объект LDAP entry

        Returns:
            Dict с полями: username, email, full_name
        """
        attrs = self.config.user_attributes

        # Безопасное извлечение атрибутов
        def get_attr(attr_name: str, default: str = "") -> str:
            try:
                value = ldap_entry[attr_name].value
                return str(value) if value else default
            except (KeyError, AttributeError):
                return default

        return {
            'username': get_attr(attrs.username),
            'email': get_attr(attrs.email),
            'full_name': get_attr(attrs.full_name),
        }

    def _get_user_groups(self, user_dn: str, connection: Connection) -> List[str]:
        """
        Получает список групп, в которых состоит пользователь.

        Args:
            user_dn: Distinguished Name пользователя
            connection: Активное LDAP подключение

        Returns:
            Список DN групп
        """
        try:
            # Формируем фильтр для поиска групп
            search_filter = self.config.group_search_filter.format(
                username=user_dn
            )

            connection.search(
                search_base=self.config.base_dn,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['cn', 'dn']
            )

            groups = [entry.entry_dn for entry in connection.entries]
            logger.debug(f"Найдено {len(groups)} групп для пользователя")

            return groups

        except LDAPException as e:
            logger.error(f"Ошибка получения групп пользователя: {e}")
            return []

    def _is_admin_user(self, user_groups: List[str]) -> bool:
        """
        Проверяет, является ли пользователь администратором.

        Args:
            user_groups: Список DN групп пользователя

        Returns:
            True если пользователь в одной из админских групп
        """
        admin_groups = self.config.admin_groups

        for group_dn in user_groups:
            if group_dn in admin_groups:
                logger.info(f"Пользователь является администратором (группа: {group_dn})")
                return True

        return False

    def search_user(self, username: str) -> Optional[Dict]:
        """
        Поиск пользователя в LDAP без аутентификации.
        Используется для синхронизации пользователей.

        Args:
            username: Имя пользователя для поиска

        Returns:
            Dict с данными пользователя или None
        """
        if not self.config.enabled:
            return None

        conn = self._get_admin_connection()
        if not conn:
            return None

        try:
            search_filter = self.config.user_search_filter.format(username=username)

            conn.search(
                search_base=self.config.base_dn,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['*']
            )

            if conn.entries:
                user_entry = conn.entries[0]
                user_data = self._extract_user_data(user_entry)

                # Получаем группы
                groups = self._get_user_groups(user_entry.entry_dn, conn)
                user_data['groups'] = groups
                user_data['is_admin'] = self._is_admin_user(groups)

                return user_data

            return None

        except LDAPException as e:
            logger.error(f"Ошибка поиска пользователя {username}: {e}")
            return None
        finally:
            conn.unbind()


# Глобальный экземпляр сервиса
ldap_service = LDAPService()
