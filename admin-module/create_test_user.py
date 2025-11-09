"""
Скрипт для создания тестового пользователя.
Используется для тестирования auth системы.
"""

import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.user import User, UserRole, UserStatus
from app.services.auth_service import auth_service


async def create_test_user():
    """Создание тестового пользователя admin."""
    async with AsyncSessionLocal() as session:
        # Проверяем существует ли пользователь
        stmt = select(User).where(User.username == "admin")
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print(f"User 'admin' already exists (ID: {existing_user.id})")
            return

        # Создаем нового пользователя
        hashed_password = auth_service.hash_password("admin123")

        user = User(
            username="admin",
            email="admin@artstore.local",
            first_name="Admin",
            last_name="User",
            hashed_password=hashed_password,
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            is_system=True
        )

        session.add(user)
        await session.commit()
        await session.refresh(user)

        print(f"✅ Created test user:")
        print(f"   Username: {user.username}")
        print(f"   Email: {user.email}")
        print(f"   Password: admin123")
        print(f"   Role: {user.role.value}")
        print(f"   ID: {user.id}")


if __name__ == "__main__":
    print("Creating test user...")
    asyncio.run(create_test_user())
    print("Done!")
