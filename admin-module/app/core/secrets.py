"""
Platform-Agnostic Secret Management для Hybrid Deployment.

Поддерживает:
- Environment Variables (default, works everywhere)
- Kubernetes Secrets (k8s/k3s native)
- File-based Secrets (fallback для custom scenarios)
- Auto-detection platform с intelligent fallback chain

Architecture:
    Development  → EnvSecretProvider (.env files)
    Docker Compose → EnvSecretProvider (docker-compose environment)
    Kubernetes → KubernetesSecretProvider (mounted secrets)
    Custom → FileSecretProvider (local secret files)
"""

from abc import ABC, abstractmethod
from typing import Optional
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)


class SecretProvider(ABC):
    """
    Abstract base class для platform-agnostic secret management.

    Все providers должны реализовать:
    - get_secret(key) - получение secret value
    - is_available() - проверка доступности provider
    """

    @abstractmethod
    def get_secret(self, key: str) -> Optional[str]:
        """
        Получение secret value по ключу.

        Args:
            key: Имя secret (e.g., "JWT_PRIVATE_KEY", "AUDIT_HMAC_SECRET")

        Returns:
            str: Secret value если найден, None иначе

        Example:
            secret = provider.get_secret("JWT_PRIVATE_KEY")
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Проверка доступности provider в текущем окружении.

        Returns:
            bool: True если provider доступен, False иначе

        Example:
            if provider.is_available():
                secret = provider.get_secret("key")
        """
        pass

    def __repr__(self) -> str:
        """String representation."""
        return f"<{self.__class__.__name__}>"


class EnvSecretProvider(SecretProvider):
    """
    Environment Variables Secret Provider.

    Используется как:
    - Default provider для всех платформ
    - Primary provider для development (через .env files)
    - Primary provider для Docker Compose

    Преимущества:
    - Работает везде (универсальность)
    - Простота конфигурации
    - Поддержка .env files через python-dotenv

    Недостатки:
    - Secrets видны в process environment
    - Логируются в shell history
    """

    def get_secret(self, key: str) -> Optional[str]:
        """
        Получение secret из environment variable.

        Args:
            key: Environment variable name

        Returns:
            Optional[str]: Secret value или None

        Example:
            provider = EnvSecretProvider()
            hmac_secret = provider.get_secret("SECURITY_AUDIT_HMAC_SECRET")
        """
        value = os.getenv(key)

        if value:
            logger.debug(f"Secret '{key}' loaded from environment variable")
        else:
            logger.debug(f"Secret '{key}' not found in environment variables")

        return value

    def is_available(self) -> bool:
        """
        Environment variables всегда доступны.

        Returns:
            bool: Always True
        """
        return True


class KubernetesSecretProvider(SecretProvider):
    """
    Kubernetes Secret Provider для k8s/k3s deployments.

    Kubernetes монтирует Secrets как файлы в pod filesystem:
    - Путь по умолчанию: /var/run/secrets/artstore/
    - Каждый secret - отдельный файл
    - Имя файла = имя secret key

    Преимущества:
    - Native k8s integration
    - RBAC protection
    - Encrypted at rest (etcd)
    - Automatic updates при изменении Secret

    Недостатки:
    - Работает только в Kubernetes
    - Требует правильной конфигурации Volume mounts

    Example k8s Secret:
        apiVersion: v1
        kind: Secret
        metadata:
          name: artstore-secrets
        type: Opaque
        stringData:
          SECURITY_AUDIT_HMAC_SECRET: "your-secret-here"
          JWT_PRIVATE_KEY: |
            -----BEGIN RSA PRIVATE KEY-----
            ...
            -----END RSA PRIVATE KEY-----

    Example Volume mount в Pod:
        volumes:
        - name: secrets
          secret:
            secretName: artstore-secrets
        containers:
        - name: admin-module
          volumeMounts:
          - name: secrets
            mountPath: /var/run/secrets/artstore
            readOnly: true
    """

    def __init__(self, secrets_path: str = "/var/run/secrets/artstore"):
        """
        Инициализация Kubernetes Secret Provider.

        Args:
            secrets_path: Путь к монтированным k8s Secrets (default: /var/run/secrets/artstore)
        """
        self.secrets_path = Path(secrets_path)

    def get_secret(self, key: str) -> Optional[str]:
        """
        Получение secret из k8s Secret mount.

        Args:
            key: Secret key name (соответствует имени файла)

        Returns:
            Optional[str]: Secret value или None

        Example:
            provider = KubernetesSecretProvider()
            hmac_secret = provider.get_secret("SECURITY_AUDIT_HMAC_SECRET")
            # Reads from /var/run/secrets/artstore/SECURITY_AUDIT_HMAC_SECRET
        """
        secret_file = self.secrets_path / key

        if not secret_file.exists():
            logger.debug(f"Secret '{key}' not found at {secret_file}")
            return None

        try:
            with open(secret_file, 'r', encoding='utf-8') as f:
                value = f.read().strip()

            logger.info(f"Secret '{key}' loaded from Kubernetes Secret mount: {secret_file}")
            return value

        except Exception as e:
            logger.error(f"Failed to read secret '{key}' from {secret_file}: {e}")
            return None

    def is_available(self) -> bool:
        """
        Проверка доступности Kubernetes Secrets.

        Проверяет наличие:
        1. /var/run/secrets/kubernetes.io (k8s service account)
        2. Configured secrets path

        Returns:
            bool: True если running в Kubernetes, False иначе
        """
        # Проверка k8s service account token (standard k8s indicator)
        k8s_sa_token = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")

        if not k8s_sa_token.exists():
            logger.debug("Not running in Kubernetes (no service account token)")
            return False

        # Проверка secrets path
        if not self.secrets_path.exists():
            logger.warning(
                f"Running in Kubernetes but secrets path {self.secrets_path} not found. "
                "Check Volume mounts configuration."
            )
            return False

        logger.info(f"Kubernetes Secret Provider available at {self.secrets_path}")
        return True


class FileSecretProvider(SecretProvider):
    """
    File-based Secret Provider для custom deployment scenarios.

    Использует локальные файлы для хранения secrets:
    - Путь по умолчанию: ./secrets/
    - Каждый secret - отдельный файл
    - Имя файла = имя secret key

    Преимущества:
    - Работает везде
    - Простота для development/testing
    - Permissions control через filesystem

    Недостатки:
    - Требует ручного управления файлами
    - Риск случайного commit в Git (.gitignore критичен!)
    - Нет automatic rotation

    Security Notes:
    - ОБЯЗАТЕЛЬНО добавить secrets/ в .gitignore
    - Установить restrictive permissions (chmod 600)
    - Использовать только для development/testing
    """

    def __init__(self, secrets_dir: str = "./secrets"):
        """
        Инициализация File-based Secret Provider.

        Args:
            secrets_dir: Путь к директории с secret файлами (default: ./secrets)
        """
        self.secrets_dir = Path(secrets_dir)

    def get_secret(self, key: str) -> Optional[str]:
        """
        Получение secret из файла.

        Args:
            key: Secret key name (соответствует имени файла)

        Returns:
            Optional[str]: Secret value или None

        Example:
            provider = FileSecretProvider()
            hmac_secret = provider.get_secret("SECURITY_AUDIT_HMAC_SECRET")
            # Reads from ./secrets/SECURITY_AUDIT_HMAC_SECRET
        """
        secret_file = self.secrets_dir / key

        if not secret_file.exists():
            logger.debug(f"Secret '{key}' not found at {secret_file}")
            return None

        try:
            with open(secret_file, 'r', encoding='utf-8') as f:
                value = f.read().strip()

            logger.info(f"Secret '{key}' loaded from file: {secret_file}")
            return value

        except Exception as e:
            logger.error(f"Failed to read secret '{key}' from {secret_file}: {e}")
            return None

    def is_available(self) -> bool:
        """
        Проверка доступности file-based secrets.

        Returns:
            bool: True если secrets directory существует, False иначе
        """
        available = self.secrets_dir.exists() and self.secrets_dir.is_dir()

        if available:
            logger.info(f"File Secret Provider available at {self.secrets_dir}")
        else:
            logger.debug(f"Secrets directory {self.secrets_dir} not found")

        return available


class HybridSecretProvider(SecretProvider):
    """
    Hybrid Secret Provider с auto-detection и intelligent fallback chain.

    Fallback chain:
    1. KubernetesSecretProvider (если в k8s)
    2. EnvSecretProvider (всегда доступен)
    3. FileSecretProvider (если secrets/ существует)

    Auto-detection logic:
    - Проверяет /var/run/secrets/kubernetes.io → k8s
    - Иначе → environment variables
    - Если secrets/ существует → добавляет в fallback chain

    Example:
        provider = get_secret_provider()
        # Auto-detects platform и выбирает appropriate provider

        hmac_secret = provider.get_secret("SECURITY_AUDIT_HMAC_SECRET")
        # Tries: k8s → env → file (в зависимости от availability)
    """

    def __init__(self, providers: Optional[list[SecretProvider]] = None):
        """
        Инициализация Hybrid Provider.

        Args:
            providers: List of providers в порядке приоритета (опционально)
                      Если None - используется auto-detection
        """
        if providers is None:
            providers = self._auto_detect_providers()

        self.providers = providers
        self._log_provider_chain()

    def _auto_detect_providers(self) -> list[SecretProvider]:
        """
        Auto-detection доступных providers с intelligent ordering.

        Returns:
            list[SecretProvider]: Ordered list of available providers

        Detection logic:
        1. Check для Kubernetes (highest priority в production)
        2. Always include EnvSecretProvider (universal fallback)
        3. Check для FileSecretProvider (development fallback)
        """
        providers = []

        # 1. Kubernetes Secret Provider (production priority)
        k8s_provider = KubernetesSecretProvider()
        if k8s_provider.is_available():
            providers.append(k8s_provider)
            logger.info("Kubernetes Secret Provider detected and enabled")

        # 2. Environment Variables (always available)
        env_provider = EnvSecretProvider()
        providers.append(env_provider)
        logger.info("Environment Variable Secret Provider enabled")

        # 3. File-based Secrets (development/testing fallback)
        file_provider = FileSecretProvider()
        if file_provider.is_available():
            providers.append(file_provider)
            logger.info("File Secret Provider detected and enabled")

        return providers

    def _log_provider_chain(self):
        """Log configured provider chain для debugging."""
        provider_names = [p.__class__.__name__ for p in self.providers]
        logger.info(f"Secret Provider chain: {' → '.join(provider_names)}")

    def get_secret(self, key: str) -> Optional[str]:
        """
        Получение secret через fallback chain.

        Пробует каждый provider в порядке приоритета до первого успеха.

        Args:
            key: Secret key name

        Returns:
            Optional[str]: Secret value или None если не найден ни в одном provider

        Example:
            provider = HybridSecretProvider()
            secret = provider.get_secret("JWT_PRIVATE_KEY")
            # Tries: k8s → env → file (останавливается на первом успехе)
        """
        for provider in self.providers:
            value = provider.get_secret(key)
            if value is not None:
                logger.debug(
                    f"Secret '{key}' resolved via {provider.__class__.__name__}"
                )
                return value

        logger.warning(
            f"Secret '{key}' not found in any provider. "
            f"Tried: {[p.__class__.__name__ for p in self.providers]}"
        )
        return None

    def is_available(self) -> bool:
        """
        Hybrid provider всегда available (минимум EnvSecretProvider).

        Returns:
            bool: Always True
        """
        return len(self.providers) > 0


# Global singleton instance
_secret_provider: Optional[HybridSecretProvider] = None


def get_secret_provider(force_reload: bool = False) -> HybridSecretProvider:
    """
    Получение singleton instance HybridSecretProvider с auto-detection.

    Args:
        force_reload: Принудительный reload provider chain (default: False)

    Returns:
        HybridSecretProvider: Configured secret provider

    Example:
        provider = get_secret_provider()
        hmac_secret = provider.get_secret("SECURITY_AUDIT_HMAC_SECRET")
        jwt_key = provider.get_secret("JWT_PRIVATE_KEY")
    """
    global _secret_provider

    if _secret_provider is None or force_reload:
        _secret_provider = HybridSecretProvider()
        logger.info("Secret Provider initialized with auto-detection")

    return _secret_provider


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Helper function для быстрого получения secret.

    Args:
        key: Secret key name
        default: Default value если secret не найден (опционально)

    Returns:
        Optional[str]: Secret value или default

    Example:
        hmac_secret = get_secret("SECURITY_AUDIT_HMAC_SECRET")
        jwt_key = get_secret("JWT_PRIVATE_KEY", default="fallback-key")
    """
    provider = get_secret_provider()
    value = provider.get_secret(key)

    return value if value is not None else default
