"""
Migration script to add legal name fields to users table
"""

from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

def migrate():
    """Add legal name columns to users table"""
    engine = create_engine(DATABASE_URL)
    
    print("🔧 Adding legal name fields to users table...")
    
    try:
        with engine.connect() as connection:
            trans = connection.begin()
            try:
                # Add legal name columns
                migrations = [
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS legal_name_first VARCHAR(255)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS legal_name_father VARCHAR(255)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS legal_name_grandfather VARCHAR(255)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS legal_name_great_grandfather VARCHAR(255)"
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
