# Этот файл нужен для того, чтобы Alembic мог найти все модели.
# Импортируйте сюда все ваши модели SQLAlchemy.

from app.db.base_class import Base  # noqa
from app.db.models.user import User, Group  # noqa