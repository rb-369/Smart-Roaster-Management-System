from fastapi import APIRouter

from models import (
    Allocation,
    Brand,
    BrandProcessRule,
    Employee,
    Pod,
    Process,
)
from routers._crud import register_crud_routes
from seed import seed_database

router = APIRouter(prefix="/api", tags=["Entities"])

register_crud_routes(router, "/pods", Pod, prefix="POD-", pad=0)
register_crud_routes(router, "/processes", Process, prefix="PROC-", pad=0)
register_crud_routes(router, "/employees", Employee, prefix="EMP-", pad=2)
register_crud_routes(router, "/brands", Brand, prefix="BRD-", pad=2)
register_crud_routes(router, "/rules", BrandProcessRule, prefix="BPR-", pad=2)
register_crud_routes(router, "/allocations", Allocation, prefix="ALC-", pad=2)


@router.post("/admin/reset-seed", tags=["Admin"])
def reset_seed():
    """Reset the database to the canonical sample_data.json state."""
    seed_database()
    return {"status": "ok", "message": "Database reset to sample_data.json"}
