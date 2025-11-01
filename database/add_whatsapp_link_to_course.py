# add_whatsapp_link_to_course.py

import logging
from sqlalchemy import create_engine, inspect, text
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_whatsapp_link_column():
    """
    Adds the 'whatsapp_group_link' column to the 'courses' table if it doesn't exist.
    """
    engine = create_engine(config.DATABASE_URL)
    inspector = inspect(engine)
    
    try:
        columns = inspector.get_columns('courses')
        column_names = [col['name'] for col in columns]
        
        if 'whatsapp_group_link' not in column_names:
            logger.info("Column 'whatsapp_group_link' not found. Adding it to 'courses' table...")
            with engine.connect() as connection:
                trans = connection.begin()
                try:
                    connection.execute(text(
                        'ALTER TABLE courses ADD COLUMN whatsapp_group_link VARCHAR(500)'
                    ))
                    trans.commit()
                    logger.info("✅ Column 'whatsapp_group_link' added successfully.")
                except Exception as e:
                    trans.rollback()
                    logger.error(f"❌ Failed to add column: {e}")
        else:
            logger.info("✅ Column 'whatsapp_group_link' already exists in 'courses' table.")
            
    except Exception as e:
        logger.error(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    add_whatsapp_link_column()
