"""
Migration script to add CourseReview and NotificationPreference tables
"""
from sqlalchemy import create_engine
from database.models import Base, CourseReview, NotificationPreference
import config

def migrate():
    """Create new tables"""
    engine = create_engine(config.DATABASE_URL)
    
    # Create only the new tables
    CourseReview.__table__.create(engine, checkfirst=True)
    NotificationPreference.__table__.create(engine, checkfirst=True)
    
    print("✅ Migration complete! New tables created:")
    print("   - course_reviews")
    print("   - notification_preferences")

if __name__ == "__main__":
    migrate()
