"""
Add is_admin field to users table
Run this once to update existing database
"""
from sqlalchemy import create_engine, text
import config

def add_is_admin_column():
    """Add is_admin column to users table"""
    engine = create_engine(config.DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            # Add is_admin column with default False
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0 NOT NULL"
            ))
            conn.commit()
            print("✅ Successfully added is_admin column to users table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠️ Column is_admin already exists")
            else:
                print(f"❌ Error: {e}")
                raise

def add_telegram_group_id_column():
    """Add telegram_group_id column to courses table"""
    engine = create_engine(config.DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            # Add telegram_group_id column
            conn.execute(text(
                "ALTER TABLE courses ADD COLUMN telegram_group_id VARCHAR(100)"
            ))
            conn.commit()
            print("✅ Successfully added telegram_group_id column to courses table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠️ Column telegram_group_id already exists")
            else:
                print(f"❌ Error: {e}")
                raise

if __name__ == "__main__":
    print("Running database migrations...")
    add_is_admin_column()
    add_telegram_group_id_column()
    print("✅ Migration complete!")
