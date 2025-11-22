"""
Password Policy Infrastructure для Admin Module.

Sprint 16 Phase 1: Strong Random Password Infrastructure
- Password strength validation с настраиваемыми правилами
- Cryptographically secure password generation
- Password history tracking для предотвращения reuse
- Password expiration enforcement
"""

import re
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from passlib.context import CryptContext


class PasswordPolicy:
    """
    Политика паролей для системы.

    Определяет требования к сложности паролей согласно best practices:
    - Минимальная длина: 12 символов (NIST рекомендует 8+, мы используем 12 для повышенной безопасности)
    - Обязательные символы: uppercase, lowercase, digits, special chars
    - Password expiration: 90 дней (configurable)
    - Password history: запрет reuse последних 5 паролей
    """

    def __init__(
        self,
        min_length: int = 12,
        require_uppercase: bool = True,
        require_lowercase: bool = True,
        require_digits: bool = True,
        require_special: bool = True,
        max_age_days: int = 90,
        history_size: int = 5
    ):
        """
        Инициализация password policy.

        Args:
            min_length: Минимальная длина пароля (default: 12)
            require_uppercase: Требовать uppercase буквы (default: True)
            require_lowercase: Требовать lowercase буквы (default: True)
            require_digits: Требовать цифры (default: True)
            require_special: Требовать специальные символы (default: True)
            max_age_days: Максимальный возраст пароля в днях (default: 90)
            history_size: Количество старых паролей для проверки (default: 5)
        """
        self.min_length = min_length
        self.require_uppercase = require_uppercase
        self.require_lowercase = require_lowercase
        self.require_digits = require_digits
        self.require_special = require_special
        self.max_age_days = max_age_days
        self.history_size = history_size

        # Special characters разрешенные для паролей
        self.special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"


class PasswordValidator:
    """
    Валидатор паролей согласно PasswordPolicy.

    Проверяет compliance с политикой безопасности паролей.
    """

    def __init__(self, policy: PasswordPolicy):
        """
        Инициализация валидатора с заданной политикой.

        Args:
            policy: Политика паролей для валидации
        """
        self.policy = policy

    def validate(self, password: str) -> tuple[bool, Optional[str]]:
        """
        Валидация пароля согласно политике.

        Args:
            password: Пароль для проверки

        Returns:
            Tuple (is_valid, error_message):
                - is_valid: True если пароль соответствует политике
                - error_message: None если valid, иначе описание ошибки
        """
        # Проверка минимальной длины
        if len(password) < self.policy.min_length:
            return False, f"Password must be at least {self.policy.min_length} characters long"

        # Проверка uppercase
        if self.policy.require_uppercase and not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"

        # Проверка lowercase
        if self.policy.require_lowercase and not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"

        # Проверка digits
        if self.policy.require_digits and not re.search(r'\d', password):
            return False, "Password must contain at least one digit"

        # Проверка special characters
        if self.policy.require_special:
            special_pattern = f"[{re.escape(self.policy.special_chars)}]"
            if not re.search(special_pattern, password):
                return False, f"Password must contain at least one special character ({self.policy.special_chars})"

        # Пароль валиден
        return True, None

    def get_strength_score(self, password: str) -> int:
        """
        Вычисление силы пароля (0-4 score).

        Простая эвристика на базе длины и разнообразия символов.
        Для production можно интегрировать zxcvbn library.

        Args:
            password: Пароль для оценки

        Returns:
            Score от 0 (слабый) до 4 (очень сильный)
        """
        score = 0

        # Длина
        if len(password) >= 12:
            score += 1
        if len(password) >= 16:
            score += 1

        # Разнообразие символов
        has_lower = bool(re.search(r'[a-z]', password))
        has_upper = bool(re.search(r'[A-Z]', password))
        has_digit = bool(re.search(r'\d', password))
        has_special = bool(re.search(f"[{re.escape(self.policy.special_chars)}]", password))

        char_variety = sum([has_lower, has_upper, has_digit, has_special])

        if char_variety >= 3:
            score += 1
        if char_variety == 4:
            score += 1

        return min(score, 4)


class PasswordGenerator:
    """
    Генератор криптографически стойких паролей.

    Использует secrets module для CSPRNG (Cryptographically Secure Pseudo-Random Number Generator).
    """

    def __init__(self, policy: PasswordPolicy):
        """
        Инициализация генератора с заданной политикой.

        Args:
            policy: Политика паролей для генерации
        """
        self.policy = policy

    def generate(self, length: Optional[int] = None) -> str:
        """
        Генерация случайного пароля согласно политике.

        Использует cryptographically secure random для безопасной генерации.
        Гарантирует наличие всех требуемых типов символов.

        Args:
            length: Длина пароля (default: policy.min_length + 4)

        Returns:
            Сгенерированный пароль
        """
        if length is None:
            length = self.policy.min_length + 4

        if length < self.policy.min_length:
            length = self.policy.min_length

        # Подготовка наборов символов
        chars = []
        required_chars = []

        if self.policy.require_lowercase:
            chars.append(string.ascii_lowercase)
            required_chars.append(secrets.choice(string.ascii_lowercase))

        if self.policy.require_uppercase:
            chars.append(string.ascii_uppercase)
            required_chars.append(secrets.choice(string.ascii_uppercase))

        if self.policy.require_digits:
            chars.append(string.digits)
            required_chars.append(secrets.choice(string.digits))

        if self.policy.require_special:
            chars.append(self.policy.special_chars)
            required_chars.append(secrets.choice(self.policy.special_chars))

        # Объединение всех допустимых символов
        all_chars = ''.join(chars)

        # Генерация оставшихся символов
        remaining_length = length - len(required_chars)
        password_chars = required_chars + [
            secrets.choice(all_chars) for _ in range(remaining_length)
        ]

        # Перемешивание символов для рандомизации позиций
        # Используем secrets.SystemRandom() для cryptographically secure shuffle
        import random
        rng = random.SystemRandom()
        rng.shuffle(password_chars)

        return ''.join(password_chars)


class PasswordHistory:
    """
    Управление историей паролей для предотвращения reuse.

    Хранит hashed историю паролей и проверяет новые пароли против неё.
    """

    def __init__(self, policy: PasswordPolicy):
        """
        Инициализация password history manager.

        Args:
            policy: Политика паролей (для history_size)
        """
        self.policy = policy
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def check_reuse(self, new_password: str, password_history: list[str]) -> bool:
        """
        Проверка нового пароля на совпадение с историей.

        Args:
            new_password: Новый пароль (plain text)
            password_history: Список старых хешированных паролей

        Returns:
            True если пароль найден в истории (ЗАПРЕЩЕН для использования)
            False если пароль не найден в истории (РАЗРЕШЕН)
        """
        if not password_history:
            return False

        # Проверяем только последние N паролей согласно policy
        recent_history = password_history[-self.policy.history_size:]

        for old_hash in recent_history:
            if self.pwd_context.verify(new_password, old_hash):
                return True  # Пароль найден в истории - запрещен

        return False  # Пароль не найден - разрешен

    def add_to_history(
        self,
        password_hash: str,
        current_history: list[str]
    ) -> list[str]:
        """
        Добавление нового пароля в историю с соблюдением history_size limit.

        Args:
            password_hash: Хеш нового пароля
            current_history: Текущая история паролей

        Returns:
            Обновленная история паролей (limited by history_size)
        """
        updated_history = current_history.copy()
        updated_history.append(password_hash)

        # Ограничиваем размер истории
        if len(updated_history) > self.policy.history_size:
            # Удаляем самые старые пароли
            updated_history = updated_history[-self.policy.history_size:]

        return updated_history


class PasswordExpiration:
    """
    Управление сроком действия паролей.

    Отслеживает expiration dates и предупреждает о необходимости смены пароля.
    """

    def __init__(self, policy: PasswordPolicy):
        """
        Инициализация password expiration manager.

        Args:
            policy: Политика паролей (для max_age_days)
        """
        self.policy = policy

    def calculate_expiration_date(
        self,
        password_changed_at: datetime
    ) -> datetime:
        """
        Вычисление даты истечения срока пароля.

        Args:
            password_changed_at: Дата последней смены пароля

        Returns:
            Дата истечения срока действия пароля
        """
        return password_changed_at + timedelta(days=self.policy.max_age_days)

    def is_expired(
        self,
        password_changed_at: datetime,
        current_time: Optional[datetime] = None
    ) -> bool:
        """
        Проверка истечения срока действия пароля.

        Args:
            password_changed_at: Дата последней смены пароля
            current_time: Текущее время (default: datetime.utcnow())

        Returns:
            True если пароль истек
        """
        if current_time is None:
            current_time = datetime.utcnow()

        expiration_date = self.calculate_expiration_date(password_changed_at)
        return current_time >= expiration_date

    def days_until_expiration(
        self,
        password_changed_at: datetime,
        current_time: Optional[datetime] = None
    ) -> int:
        """
        Вычисление количества дней до истечения срока пароля.

        Args:
            password_changed_at: Дата последней смены пароля
            current_time: Текущее время (default: datetime.utcnow())

        Returns:
            Количество дней до истечения (отрицательное если уже истек)
        """
        if current_time is None:
            current_time = datetime.utcnow()

        expiration_date = self.calculate_expiration_date(password_changed_at)
        delta = expiration_date - current_time
        return delta.days

    def needs_warning(
        self,
        password_changed_at: datetime,
        warning_days: int = 14,
        current_time: Optional[datetime] = None
    ) -> bool:
        """
        Проверка необходимости предупреждения о скором истечении пароля.

        Args:
            password_changed_at: Дата последней смены пароля
            warning_days: За сколько дней предупреждать (default: 14)
            current_time: Текущее время (default: datetime.utcnow())

        Returns:
            True если нужно показать предупреждение
        """
        days_left = self.days_until_expiration(password_changed_at, current_time)
        return 0 < days_left <= warning_days
