"""
Add certificate registration feature
"""
from sqlalchemy import text
from database import engine

def upgrade():
    with engine.connect() as conn:
        # Add certificate fields to courses table
        conn.execute(text("""
        ALTER TABLE courses
        ADD COLUMN IF NOT EXISTS certificate_price FLOAT DEFAULT 0 NOT NULL,
        ADD COLUMN IF NOT EXISTS certificate_available BOOLEAN DEFAULT TRUE NOT NULL;
        """))
        
        # Add certificate field to enrollments table
        conn.execute(text("""
        ALTER TABLE enrollments
        ADD COLUMN IF NOT EXISTS with_certificate BOOLEAN DEFAULT FALSE NOT NULL;
        """))
        
        # Add certificate field to cart table
        conn.execute(text("""
        ALTER TABLE cart
        ADD COLUMN IF NOT EXISTS with_certificate BOOLEAN DEFAULT FALSE NOT NULL;
        """))
        
        conn.commit()
        print("✅ Migration complete: Added certificate feature columns")

if __name__ == "__main__":
    upgrade()
