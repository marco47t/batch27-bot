"""
Database initialization and session management
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
import logging

from .models import Base
import config

logger = logging.getLogger(__name__)

# Create engine
engine = create_engine(
    config.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database - Create all tables"""
    try:
        # Import all models to ensure they're registered
        from . import models
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created successfully!")
        
    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}")
        raise


@contextmanager
def get_db() -> Session:
    """Get database session context manager"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
