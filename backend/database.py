import os
from typing import Generator
from sqlmodel import SQLModel, create_engine, Session

# Support DATABASE_URL for Postgres (Render/Supabase) or SQLite for local dev
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./roster.db")

# SQLite needs check_same_thread=False
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# Handle Postgres dialect format from Render/Supabase if needed
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
