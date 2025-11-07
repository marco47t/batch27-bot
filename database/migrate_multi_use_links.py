"""
Migration script to adapt the payment_links table for multi-use functionality.
"""
import os
import sys
from sqlalchemy import create_engine, inspect, text
import logging

# Add project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """
    Applies schema changes to the payment_links table by rebuilding it.
    This is necessary to handle dropping columns with foreign key constraints in SQLite.
    """
    engine = create_engine(config.DATABASE_URL)
    inspector = inspect(engine)
    
    table_name = 'payment_links'
    
    if not inspector.has_table(table_name):
        logger.warning(f"Table '{table_name}' not found. Skipping migration.")
        return

    columns = [col['name'] for col in inspector.get_columns(table_name)]
    
    # If the old columns don't exist and the new one does, migration is already done.
    if 'used_by_user_id' not in columns and 'usage_count' in columns:
        logger.info("Migration appears to have already been applied. Skipping.")
        return

    with engine.connect() as connection:
        trans = connection.begin()
        try:
            logger.info(f"Starting migration for table '{table_name}' by rebuilding it.")

            # Disable foreign keys during the transaction
            connection.execute(text('PRAGMA foreign_keys=OFF'))
            logger.info("Temporarily disabled foreign key checks.")

            # 1. Rename the old table
            connection.execute(text(f'ALTER TABLE {table_name} RENAME TO {table_name}_old'))
            logger.info(f"Renamed table '{table_name}' to '{table_name}_old'.")

            # 2. Create the new table with the desired schema
            create_table_sql = """
            CREATE TABLE payment_links (
                link_id INTEGER NOT NULL,
                token VARCHAR(64) NOT NULL,
                course_id INTEGER NOT NULL,
                with_certificate BOOLEAN NOT NULL,
                usage_count INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME,
                PRIMARY KEY (link_id),
                UNIQUE (token),
                FOREIGN KEY(course_id) REFERENCES courses (course_id) ON DELETE CASCADE
            )
            """
            connection.execute(text(create_table_sql))
            logger.info(f"Created new '{table_name}' table with the updated schema.")

            # 3. Copy the data from the old table to the new one
            copy_data_sql = """
            INSERT INTO payment_links (link_id, token, course_id, with_certificate, created_at)
            SELECT link_id, token, course_id, with_certificate, created_at FROM payment_links_old
            """
            connection.execute(text(copy_data_sql))
            logger.info(f"Copied data from '{table_name}_old' to '{table_name}'.")

            # 4. Drop the old table
            connection.execute(text(f'DROP TABLE {table_name}_old'))
            logger.info(f"Dropped old table '{table_name}_old'.")
            
            trans.commit()
            logger.info("✅ Migration completed successfully!")

        except Exception as e:
            trans.rollback()
            logger.error(f"❌ Migration failed: {e}")
        finally:
            # Always re-enable foreign keys
            connection.execute(text('PRAGMA foreign_keys=ON'))
            logger.info("Re-enabled foreign key checks.")

if __name__ == "__main__":
    run_migration()
