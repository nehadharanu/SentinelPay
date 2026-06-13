from fastapi import APIRouter

from app.api.v1.endpoints import auth, transactions, rules, admin

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
router.include_router(rules.router, prefix="/rules", tags=["rules"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
