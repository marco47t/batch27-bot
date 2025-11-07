"""
Database session management and engine configuration
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
import config

# Create SQLAlchemy engine
engine = create_engine(
    config.DATABASE_URL,
    echo=config.ENVIRONMENT == 'development',  # Log SQL in development
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Create session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

@contextmanager
def get_db() -> Session:
    """
    Context manager for database sessions.
    Provides a session and handles rollback on error and closing.
    The caller is responsible for committing the session.
    """
    session = SessionLocal()
    try:
        yield session
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def init_db():
    """
    Initialize database - create all tables
    Should be called when app starts for the first time
    """
    from database.models import Base
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created successfully!")
