"""
Add amount_paid column to enrollments table
"""
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)

print("🔧 Adding amount_paid column...")

try:
    with engine.connect() as connection:
        trans = connection.begin()
        try:
            connection.execute(text(
                "ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS amount_paid FLOAT DEFAULT 0"
            ))
            # Set existing records to have amount_paid = payment_amount for verified ones
            connection.execute(text(
                "UPDATE enrollments SET amount_paid = payment_amount WHERE payment_status = 'VERIFIED' AND amount_paid = 0"
            ))
            trans.commit()
            print("✅ Migration completed!")
        except Exception as e:
            trans.rollback()
            print(f"❌ Failed: {e}")
except Exception as e:
    print(f"❌ Connection failed: {e}")
