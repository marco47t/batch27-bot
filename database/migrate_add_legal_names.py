"""
Migration script to add legal name fields to users table
"""

from sqlalchemy import text
from database.session import get_db
import logging

logger = logging.getLogger(__name__)

def migrate():
    """Add legal name columns to users table"""
    db = next(get_db())
    
    try:
        # Add legal name columns
        migrations = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS legal_name_first VARCHAR(255)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS legal_name_father VARCHAR(255)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS legal_name_grandfather VARCHAR(255)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS legal_name_great_grandfather VARCHAR(255)"
        ]
        
        for migration in migrations:
            logger.info(f"Executing: {migration}")
            db.execute(text(migration))
        
        db.commit()
        logger.info("✅ Successfully added legal name fields to users table")
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Migration failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
