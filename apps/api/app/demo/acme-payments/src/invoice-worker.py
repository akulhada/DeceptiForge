import fastapi

DATABASE_URL = "postgresql://payments@localhost/payments"
router = fastapi.APIRouter()
router.get("/v1/customer-profiles")
