# scripts/populate_db.py

from datetime import datetime, timedelta, timezone
import os
import sys

# Add project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import crud, get_db, init_db
from database.models import PaymentStatus, TransactionStatus

def populate_database():
    """Populates the database with sample data for testing."""
    print("Initializing database...")
    init_db()
    print("Database initialized.")

    with get_db() as session:
        print("Populating data...")

        # Create Instructors
        instructor1 = crud.create_instructor(session, name="Dr. Ahmed Ali", specialization="Python & Data Science")
        instructor2 = crud.create_instructor(session, name="Eng. Fatima Salah", specialization="Web Development")
        print(f"Created instructors: {instructor1.name}, {instructor2.name}")

        # Create Courses
        course1 = crud.create_course(
            session,
            course_name="Introduction to Python",
            description="A beginner-friendly course on Python programming.",
            price=3000.0,
            certificate_price=2000.0,
            certificate_available=True,
            instructor_id=instructor1.instructor_id,
            start_date=datetime.now(timezone.utc) + timedelta(days=10),
            end_date=datetime.now(timezone.utc) + timedelta(days=40)
        )
        course2 = crud.create_course(
            session,
            course_name="Advanced Web Development",
            description="Master front-end and back-end web development.",
            price=120.0,
            certificate_price=25.0,
            certificate_available=True,
            instructor_id=instructor2.instructor_id,
            start_date=datetime.now(timezone.utc) + timedelta(days=5),
            end_date=datetime.now(timezone.utc) + timedelta(days=65)
        )
        course3 = crud.create_course(
            session,
            course_name="Data Analysis with Pandas",
            description="Learn data analysis using the Pandas library.",
            price=75.0,
            instructor_id=instructor1.instructor_id,
            start_date=datetime.now(timezone.utc) + timedelta(days=20),
            end_date=datetime.now(timezone.utc) + timedelta(days=50)
        )
        print(f"Created courses: {course1.course_name}, {course2.course_name}, {course3.course_name}")

        # Create Users
        user1 = crud.get_or_create_user(session, telegram_user_id=111111, first_name="Test", last_name="User 1", chat_id=111111)
        user2 = crud.get_or_create_user(session, telegram_user_id=222222, first_name="Test", last_name="User 2", chat_id=222222)
        user3 = crud.get_or_create_user(session, telegram_user_id=333333, first_name="Test", last_name="User 3", chat_id=333333)
        print(f"Created users: {user1.first_name}, {user2.first_name}, {user3.first_name}")

        # Create Enrollments
        enrollment1 = crud.create_enrollment(session, user_id=user1.user_id, course_id=course1.course_id, payment_amount=60.0)
        enrollment1.with_certificate = True
        enrollment1.amount_paid = 60.0  # Set amount_paid for verified enrollment
        crud.update_enrollment_status(session, enrollment_id=enrollment1.enrollment_id, status="VERIFIED")

        # Add a transaction for enrollment1
        transaction1 = crud.create_transaction(
            session,
            enrollment_id=enrollment1.enrollment_id,
            receipt_image_path="path/to/receipt1.jpg"
        )
        crud.update_transaction(
            session,
            transaction_id=transaction1.transaction_id,
            status=TransactionStatus.APPROVED, # Use the enum directly
            receipt_amount=60.0,
            receipt_transaction_id="TXN12345",
            receipt_transfer_datetime=datetime.now(timezone.utc)
        )

        enrollment2 = crud.create_enrollment(session, user_id=user2.user_id, course_id=course2.course_id, payment_amount=120.0)
        
        enrollment3 = crud.create_enrollment(session, user_id=user1.user_id, course_id=course3.course_id, payment_amount=75.0)
        enrollment3.payment_status = PaymentStatus.FAILED
        print("Created enrollments.")

        # Add items to cart
        crud.add_to_cart(session, user_id=user3.user_id, course_id=course1.course_id)
        crud.add_to_cart_with_certificate(session, user_id=user3.user_id, course_id=course2.course_id, with_certificate=True)
        print("Added items to cart for User 3.")

        session.commit()
        print("Data population complete!")

if __name__ == "__main__":
    populate_database()
