"""
Add receipt details to Transaction table and create index
"""
from sqlalchemy import text
from database import engine

def upgrade():
    with engine.connect() as conn:
        # Add new columns
        conn.execute(text("""
            ALTER TABLE transactions 
            ADD COLUMN IF NOT EXISTS receipt_transaction_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS receipt_transfer_date TIMESTAMP,
            ADD COLUMN IF NOT EXISTS receipt_sender_name VARCHAR(255),
            ADD COLUMN IF NOT EXISTS receipt_amount FLOAT;
        """))
        
        # Create index on receipt_transaction_id for fast duplicate lookup
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_receipt_transaction_id 
            ON transactions(receipt_transaction_id);
        """))
        
        conn.commit()
        print("✅ Migration complete: Added receipt fields to Transaction table")

if __name__ == "__main__":
    upgrade()
