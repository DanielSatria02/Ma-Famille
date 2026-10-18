from fastapi import APIRouter

from app.api.v1 import (
    availability,
    bookings,
    courts,
    facilities,
    health,
    manager,
    payments,
    pricing,
    slots,
    venues,
)

# All v1 routers wired. Keep this file as the single v1 composition root.
router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(venues.router)
router.include_router(courts.router)
router.include_router(slots.router)
router.include_router(availability.router)
router.include_router(pricing.router)
router.include_router(facilities.router)
router.include_router(bookings.router)
router.include_router(payments.router)
router.include_router(manager.router)
