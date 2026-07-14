from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_admin
from app.models import User
from app.schemas import AdminSettingsUpdate
from app.services.admin_settings import SettingsFileError, read_admin_settings, update_admin_settings


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/settings")
def get_settings(current_user: User = Depends(require_admin)):
    return read_admin_settings()


@router.put("/settings")
def update_settings(payload: AdminSettingsUpdate, current_user: User = Depends(require_admin)):
    try:
        return update_admin_settings(payload.values)
    except SettingsFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
