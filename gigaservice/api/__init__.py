from fastapi import APIRouter
from .packages import router as packages_router
from .sensors import router as sensors_router
from .trackers import router as trackers_router

router = APIRouter()
router.include_router(packages_router)
router.include_router(sensors_router)
router.include_router(trackers_router)
