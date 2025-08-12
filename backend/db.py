"""
Database initialization and session management for FastAPI (SQLAlchemy 2.0+).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/postgres")

engine = create_engine(
    DATABASE_URL, connect_args={}
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)

def get_db():
    """Yield a DB session and close it after use (FastAPI dependency style)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
