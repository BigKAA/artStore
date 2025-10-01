"""
Сервис для работы с OAuth2/OIDC провайдерами.
Поддерживает множественных провайдеров (Dex, Google, Azure AD и др.)
"""
from authlib.integrations.starlette_client import OAuth
from authlib.oauth2.rfc6749 import OAuth2Token
from typing import Optional, Dict, List, Tuple
import httpx
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OAuth2Service:
    """
    Сервис для интеграции с OAuth2/OIDC провайдерами.

    Основные функции:
    - Инициализация OAuth2 клиентов для каждого провайдера
    - Получение authorization URL для redirect
    - Обмен authorization code на access token
    - Получение информации о пользователе
    - Проверка прав администратора
    """

    def __init__(self):
        """Инициализация OAuth2 сервиса"""
        self.config = settings.auth.oauth2
        self.oauth = OAuth()
        self.providers = {}

        if not self.config.enabled:
            logger.info("OAuth2 интеграция отключена")
            return

        # Регистрация всех активных провайдеров
        for provider_name, provider_config in self.config.providers.items():
            if provider_config.enabled:
                self._register_provider(provider_name, provider_config)

        logger.info(f"OAuth2 сервис инициализирован с {len(self.providers)} провайдерами")

    def _register_provider(self, name: str, config):
        """
        Регистрирует OAuth2 провайдера.

        Args:
            name: Имя провайдера (dex, google, etc)
            config: Конфигурация провайдера
        """
        try:
            # Authlib поддерживает автоматическое получение endpoints через .well-known
            if config.server_metadata_url:
                self.oauth.register(
                    name=name,
                    client_id=config.client_id,
                    client_secret=config.client_secret,
                    server_metadata_url=config.server_metadata_url,
                    client_kwargs={
                        'scope': ' '.join(config.scopes)
                    }
                )
            else:
                # Или явная конфигурация endpoints
                self.oauth.register(
                    name=name,
                    client_id=config.client_id,
                    client_secret=config.client_secret,
                    authorize_url=config.authorize_url,
                    access_token_url=config.token_url,
                    userinfo_endpoint=config.userinfo_url,
                    jwks_uri=config.jwks_uri,
                    client_kwargs={
                        'scope': ' '.join(config.scopes)
                    }
                )

            self.providers[name] = config
            logger.info(f"OAuth2 провайдер '{name}' зарегистрирован")

        except Exception as e:
            logger.error(f"Ошибка регистрации OAuth2 провайдера '{name}': {e}")

    def get_authorization_url(
        self,
        provider_name: str,
        redirect_uri: str
    ) -> Optional[Tuple[str, str]]:
        """
        Получает URL для redirect пользователя на страницу авторизации провайдера.

        Args:
            provider_name: Имя провайдера (dex, google, etc)
            redirect_uri: URL для callback после авторизации

        Returns:
            Tuple (authorization_url, state) или None
            state используется для защиты от CSRF атак

        Example:
            >>> auth_url, state = oauth2_service.get_authorization_url("dex", "http://localhost:8000/callback")
            >>> # Сохраните state в session
            >>> # Redirect пользователя на auth_url
        """
        if provider_name not in self.providers:
            logger.error(f"Провайдер '{provider_name}' не найден")
            return None

        try:
            client = self.oauth.create_client(provider_name)

            # Authlib генерирует state автоматически
            authorization_url, state = client.create_authorization_url(
                redirect_uri=redirect_uri
            )

            logger.info(f"Создан authorization URL для провайдера '{provider_name}'")
            return authorization_url, state

        except Exception as e:
            logger.error(f"Ошибка создания authorization URL: {e}")
            return None

    async def handle_callback(
        self,
        provider_name: str,
        redirect_uri: str,
        authorization_response: str
    ) -> Optional[Dict]:
        """
        Обрабатывает callback после авторизации пользователя.
        Обменивает authorization code на access token и получает данные пользователя.

        Args:
            provider_name: Имя провайдера
            redirect_uri: URL callback (должен совпадать с тем, что был в authorization)
            authorization_response: Полный URL с query параметрами (code, state)

        Returns:
            Dict с данными пользователя или None
            содержит: username, email, full_name, is_admin, groups, provider

        Example:
            >>> # В FastAPI endpoint
            >>> user_data = await oauth2_service.handle_callback(
            >>>     "dex",
            >>>     "http://localhost:8000/callback",
            >>>     str(request.url)  # Полный URL с query params
            >>> )
        """
        if provider_name not in self.providers:
            logger.error(f"Провайдер '{provider_name}' не найден")
            return None

        try:
            client = self.oauth.create_client(provider_name)

            # Шаг 1: Обмен code на token
            token = await client.authorize_access_token(
                redirect_uri=redirect_uri,
                url=authorization_response
            )

            logger.info(f"Получен access token от провайдера '{provider_name}'")

            # Шаг 2: Получение информации о пользователе
            userinfo = await self._get_userinfo(provider_name, token)

            if not userinfo:
                return None

            # Шаг 3: Маппинг полей провайдера на нашу систему
            user_data = self._map_userinfo(provider_name, userinfo)

            # Шаг 4: Проверка прав администратора
            user_data['is_admin'] = self._is_admin_user(provider_name, userinfo)

            # Дополнительная информация
            user_data['provider'] = provider_name

            return user_data

        except Exception as e:
            logger.error(f"Ошибка обработки OAuth2 callback: {e}")
            return None

    async def _get_userinfo(
        self,
        provider_name: str,
        token: OAuth2Token
    ) -> Optional[Dict]:
        """
        Получает информацию о пользователе через userinfo endpoint.

        Args:
            provider_name: Имя провайдера
            token: OAuth2 токен

        Returns:
            Dict с данными пользователя от провайдера
        """
        try:
            client = self.oauth.create_client(provider_name)

            # Authlib автоматически использует userinfo_endpoint
            userinfo = await client.userinfo(token=token)

            logger.debug(f"Получен userinfo от '{provider_name}': {userinfo}")
            return dict(userinfo)

        except Exception as e:
            logger.error(f"Ошибка получения userinfo: {e}")
            return None

    def _map_userinfo(self, provider_name: str, userinfo: Dict) -> Dict:
        """
        Маппинг полей от OAuth2 провайдера на наши поля.

        Args:
            provider_name: Имя провайдера
            userinfo: Данные пользователя от провайдера

        Returns:
            Dict с нашими полями: username, email, full_name, groups
        """
        config = self.providers[provider_name]
        mapping = config.user_mapping

        # Безопасное извлечение значений
        def get_field(field_name: str, default: str = "") -> str:
            return userinfo.get(field_name, default)

        mapped_data = {
            'username': get_field(mapping.username),
            'email': get_field(mapping.email),
            'full_name': get_field(mapping.full_name),
        }

        # Группы (если есть)
        groups_field = mapping.groups
        groups = userinfo.get(groups_field, [])

        # Обеспечиваем что groups это список
        if isinstance(groups, str):
            groups = [groups]
        elif not isinstance(groups, list):
            groups = []

        mapped_data['groups'] = groups

        return mapped_data

    def _is_admin_user(self, provider_name: str, userinfo: Dict) -> bool:
        """
        Проверяет, является ли пользователь администратором.

        Args:
            provider_name: Имя провайдера
            userinfo: Данные пользователя от провайдера

        Returns:
            True если пользователь администратор
        """
        config = self.providers[provider_name]
        mapping = config.user_mapping

        # Проверка по группам
        if config.admin_groups:
            groups = userinfo.get(mapping.groups, [])

            if isinstance(groups, str):
                groups = [groups]

            for group in groups:
                if group in config.admin_groups:
                    logger.info(f"Пользователь администратор (группа OAuth2: {group})")
                    return True

        # Проверка по email (для провайдеров без групп, например Google)
        if config.admin_emails:
            email = userinfo.get(mapping.email)
            if email in config.admin_emails:
                logger.info(f"Пользователь администратор (email: {email})")
                return True

        return False

    def get_available_providers(self) -> List[str]:
        """
        Возвращает список доступных OAuth2 провайдеров.

        Returns:
            Список имен активных провайдеров
        """
        return list(self.providers.keys())


# Глобальный экземпляр сервиса
oauth2_service = OAuth2Service()
