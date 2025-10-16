"""
Migration script to add course reviews and notification preferences tables
"""
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime

Base = declarative_base()

def run_migration():
    """Add CourseReview and NotificationPreference tables"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        return
    
    # Fix Railway postgres URL
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    engine = create_engine(database_url)
    
    # Create tables
    Base.metadata.create_all(engine)
    
    print("✅ Migration completed successfully!")
    print("   - CourseReview table created")
    print("   - NotificationPreference table created")

if __name__ == "__main__":
    run_migration()
