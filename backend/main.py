import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from database import init_db, engine
from models import Employee
from seed import seed_database
from routers import assistant, entities, leaves, rosters

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)
load_dotenv(override=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup and auto-seed if empty
    init_db()
    with Session(engine) as session:
        if session.exec(select(Employee)).first() is None:
            seed_database()
    yield


app = FastAPI(
    title="Smart Roster Management System API",
    version="1.0.0",
    description="Deterministic operational scheduling and conflict detection API for D2C CX teams.",
    lifespan=lifespan,
)

# CORS configuration
origins_env = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,https://roster-management1.vercel.app,https://roaster-management1.vercel.app",
)
allow_origins = [orig.strip().rstrip("/") for orig in origins_env.split(",") if orig.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins or ["*"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(rosters.notifications_router)
app.include_router(rosters.router)
app.include_router(entities.router)
app.include_router(leaves.router)
app.include_router(assistant.router)


@app.get("/api/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "Smart Roster Management System Backend",
        "version": "1.0.0",
    }
