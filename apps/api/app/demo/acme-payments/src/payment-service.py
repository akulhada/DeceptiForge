import fastapi
import psycopg

DATABASE_URL = "postgresql://payments@localhost/payments"
router = fastapi.APIRouter()
router.get("/v1/customer-profiles")
