from app.services.base import CRUDBase
from app.db.models.user import Group
from app.models.user import GroupCreate, GroupUpdate


class CRUDGroup(CRUDBase[Group, GroupCreate, GroupUpdate]):
    pass


group = CRUDGroup(Group)