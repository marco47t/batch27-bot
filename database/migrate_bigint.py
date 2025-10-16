"""
Migration script to change telegram_user_id and telegram_chat_id to BigInteger
Run this ONCE on production database
"""
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in environment variables")
    exit(1)

# Create engine
engine = create_engine(DATABASE_URL)

print("🔧 Starting migration to BigInteger...")

try:
    with engine.connect() as connection:
        # Start transaction
        trans = connection.begin()
        
        try:
            # Change telegram_user_id to BIGINT
            print("📝 Changing telegram_user_id to BIGINT...")
            connection.execute(text(
                "ALTER TABLE users ALTER COLUMN telegram_user_id TYPE BIGINT"
            ))
            
            # Change telegram_chat_id to BIGINT
            print("📝 Changing telegram_chat_id to BIGINT...")
            connection.execute(text(
                "ALTER TABLE users ALTER COLUMN telegram_chat_id TYPE BIGINT"
            ))
            
            # Commit transaction
            trans.commit()
            print("✅ Migration completed successfully!")
            
        except Exception as e:
            trans.rollback()
            print(f"❌ Migration failed: {e}")
            raise
            
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    exit(1)

print("\n🎉 All done! Your database now supports large Telegram user IDs.")
