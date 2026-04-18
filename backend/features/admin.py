from fastapi import APIRouter

from backend.features.admin_containers import router as admin_containers_router
from backend.features.admin_users import router as admin_users_router


router = APIRouter()
router.include_router(admin_users_router)
router.include_router(admin_containers_router)
