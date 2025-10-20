"""
Migration to add receipt metadata fields for fraud detection
"""

from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

def migrate():
    """Add receipt metadata columns to enrollments table"""
    engine = create_engine(DATABASE_URL)
    
    print("🔧 Adding receipt metadata fields...")
    
    try:
        with engine.connect() as connection:
            trans = connection.begin()
            try:
                # Add receipt metadata columns
                migrations = [
                    "ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS receipt_transaction_id VARCHAR(100)",
                    "ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS receipt_transfer_date TIMESTAMP",
                    "ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS receipt_sender_name VARCHAR(255)",
                    "ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS receipt_submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                ]
                
                for migration in migrations:
                    print(f"Executing: {migration}")
                    connection.execute(text(migration))
                
                trans.commit()
                print("✅ Migration completed successfully!")
                
            except Exception as e:
                trans.rollback()
                print(f"❌ Migration failed: {e}")
                raise
                
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        raise

if __name__ == "__main__":
    migrate()
