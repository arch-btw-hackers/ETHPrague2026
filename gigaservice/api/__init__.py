from fastapi import APIRouter
from .auth import router as auth_router
from .packages import router as packages_router
from .sensors import router as sensors_router
from .stats import router as stats_router
from .trackers import router as trackers_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(packages_router)
router.include_router(sensors_router)
router.include_router(stats_router)
router.include_router(trackers_router)
