
import os
import sys
import boto3
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Text, DateTime, ForeignKey, Float, Boolean, Enum
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func
import enum

# Add project root to Python path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

import config

# --- SQLAlchemy Models (simplified for this script) ---
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True)
    telegram_user_id = Column(BigInteger, unique=True, nullable=False)
    first_name = Column(String(255))
    last_name = Column(String(255))

class Course(Base):
    __tablename__ = "courses"
    course_id = Column(Integer, primary_key=True)
    course_name = Column(String(255), nullable=False)

class Enrollment(Base):
    __tablename__ = "enrollments"
    enrollment_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    course_id = Column(Integer, ForeignKey("courses.course_id"))
    receipt_image_path = Column(String(500))

    user = relationship("User")
    course = relationship("Course")

# --- Database Setup ---
engine = create_engine(config.DATABASE_URL)
Session = sessionmaker(bind=engine)

# Create a directory to store the receipts
output_base_dir = "downloaded_receipts"
if not os.path.exists(output_base_dir):
    os.makedirs(output_base_dir)

# Create an S3 client
s3 = boto3.client(
    "s3",
    aws_access_key_id=config.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
    region_name=config.AWS_S3_REGION,
)

def download_receipts_from_s3_and_db():
    """
    Downloads receipts from S3, organized by user and course name,
    using information from the RDS database.
    """
    session = Session()
    try:
        # Query enrollments with user and course information
        enrollments = session.query(Enrollment).join(User).join(Course).all()

        for enrollment in enrollments:
            user_folder_name = f"{enrollment.user.telegram_user_id}"
            if enrollment.user.first_name:
                user_folder_name += f"_{enrollment.user.first_name}"
            if enrollment.user.last_name:
                user_folder_name += f"_{enrollment.user.last_name}"
            
            course_file_name = enrollment.course.course_name
            receipt_s3_key = enrollment.receipt_image_path

            if not receipt_s3_key:
                print(f"Skipping enrollment {enrollment.enrollment_id}: no receipt_image_path found.")
                continue
            
            # The receipt_image_path is a full URL, extract the key
            if '.amazonaws.com/' in receipt_s3_key:
                s3_key = receipt_s3_key.split('.amazonaws.com/')[1]
            else:
                s3_key = receipt_s3_key


            # Extract file extension from S3 key
            _, file_extension = os.path.splitext(s3_key)
            if not file_extension:
                file_extension = ".jpg" # Default to .jpg if no extension in S3 key

            # Create user-specific directory
            user_directory = os.path.join(output_base_dir, user_folder_name.replace(" ", "_"))
            if not os.path.exists(user_directory):
                os.makedirs(user_directory)

            # Define local download path
            # Sanitize course_file_name for filesystem compatibility
            safe_course_name = "".join(c for c in course_file_name if c.isalnum() or c in (' ', '.', '_')).rstrip()
            download_path = os.path.join(user_directory, f"{safe_course_name}{file_extension}")

            print(f"Downloading {s3_key} for user {user_folder_name} (Course: {course_file_name}) to {download_path}")
            try:
                s3.download_file(config.AWS_S3_BUCKET_NAME, s3_key, download_path)
            except Exception as e:
                print(f"  -> ERROR downloading {s3_key}: {e}")


        print("All receipts downloaded successfully.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    download_receipts_from_s3_and_db()
