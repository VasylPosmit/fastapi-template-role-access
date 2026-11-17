from fastapi import APIRouter, Depends
from sqlmodel import col, func, select

from app.api.deps import SessionDep, require_permission
from app.core.permissions import Permission
from app.models import Item, MetricsPublic, User

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "/",
    dependencies=[Depends(require_permission(Permission.METRICS_READ))],
    response_model=MetricsPublic,
)
def read_metrics(session: SessionDep) -> MetricsPublic:
    """
    Basic counts (stub for a real metrics page).
    """
    return MetricsPublic(
        users=session.exec(select(func.count()).select_from(User)).one(),
        active_users=session.exec(
            select(func.count()).select_from(User).where(col(User.is_active).is_(True))
        ).one(),
        items=session.exec(select(func.count()).select_from(Item)).one(),
    )
