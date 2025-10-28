"""
SQLAlchemy database models for Course Registration Bot
"""
from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import enum

Base = declarative_base()


class PaymentStatus(enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class TransactionStatus(enum.Enum):
    """Transaction review status enumeration"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class User(Base):
    """User model - stores Telegram user information"""
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    telegram_chat_id = Column(BigInteger, nullable=False)
    legal_name_first = Column(String(255), nullable=True)  # First name
    legal_name_father = Column(String(255), nullable=True)  # Father's name
    legal_name_grandfather = Column(String(255), nullable=True)  # Grandfather's name
    legal_name_great_grandfather = Column(String(255), nullable=True)  # Great grandfather's name
    registration_date = Column(DateTime, default=func.now(), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    
    # Relationships
    enrollments = relationship("Enrollment", back_populates="user", cascade="all, delete-orphan")
    cart_items = relationship("Cart", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("CourseReview", back_populates="user", cascade="all, delete-orphan")  # ✅ ADD THIS
    notification_preferences = relationship("NotificationPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")  # ✅ ADD THIS
    instructor_reviews = relationship("InstructorReview", back_populates="user")  # ← ADD THIS
    def __repr__(self):
        return f"<User {self.user_id}: {self.first_name}>"


class Course(Base):
    """Course model - stores course information"""
    __tablename__ = "courses"
    
    course_id = Column(Integer, primary_key=True, autoincrement=True)
    course_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    certificate_price = Column(Float, nullable=False, default=0)
    certificate_available = Column(Boolean, default=False, nullable=False)
    telegram_group_link = Column(String(500), nullable=True)
    telegram_group_id = Column(String(100), nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    registration_open_date = Column(DateTime, nullable=True)
    registration_close_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    max_students = Column(Integer, nullable=True)
    created_date = Column(DateTime, default=func.now(), nullable=False)
    instructor = Column(Text, nullable=True)
    instructor_id = Column(Integer, ForeignKey('instructors.instructor_id', ondelete='SET NULL'), nullable=True)  # ← ADD THIS

    # Relationships
    enrollments = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")
    cart_items = relationship("Cart", back_populates="course", cascade="all, delete-orphan")
    reviews = relationship("CourseReview", back_populates="course", cascade="all, delete-orphan")  # ✅ ADD THIS
    instructor_reviews = relationship("InstructorReview", back_populates="course", cascade="all, delete-orphan")
    instructor = relationship("Instructor", back_populates="courses")  # ← ADD THIS
    def __repr__(self):
        return f"<Course {self.course_id}: {self.course_name}>"


class Enrollment(Base):
    """Enrollment model - tracks user course registrations"""
    __tablename__ = "enrollments"
    
    enrollment_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.course_id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_date = Column(DateTime, default=func.now(), nullable=False)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    payment_amount = Column(Float, nullable=True)
    with_certificate = Column(Boolean, default=False, nullable=False)
    amount_paid = Column(Float, default=0, nullable=False)  # ✅ ADD THIS - Track partial payments
    receipt_image_path = Column(String(500), nullable=True)
    verification_date = Column(DateTime, nullable=True)
    admin_notes = Column(Text, nullable=True)
    receipt_transaction_id = Column(String(100), nullable=True)
    receipt_transfer_datetime = Column(DateTime, nullable=True)
    receipt_sender_name = Column(String(255), nullable=True)
    receipt_submission_date = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")
    transactions = relationship("Transaction", back_populates="enrollment", cascade="all, delete-orphan")
    review = relationship("CourseReview", back_populates="enrollment", uselist=False, cascade="all, delete-orphan")  # ✅ ADD THIS
    
    def __repr__(self):
        return f"<Enrollment {self.enrollment_id}: User {self.user_id} → Course {self.course_id}>"


class Transaction(Base):
    """Transaction model - stores payment receipt validation attempts"""
    __tablename__ = "transactions"
    
    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    enrollment_id = Column(Integer, ForeignKey("enrollments.enrollment_id", ondelete="CASCADE"), nullable=False, index=True)
    receipt_image_path = Column(String(500), nullable=False)
    submitted_date = Column(DateTime, default=func.now(), nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)
    admin_reviewed_by = Column(Integer, nullable=True)
    admin_review_date = Column(DateTime, nullable=True)
    
    # ✅ NEW: Store extracted receipt details
    receipt_transaction_id = Column(String(100), nullable=True, index=True)  # ✅ INDEXED for duplicate check
    receipt_transfer_datetime = Column(DateTime, nullable=True)

    receipt_sender_name = Column(String(255), nullable=True)
    receipt_amount = Column(Float, nullable=True)  # ✅ NEW: Store extracted amount
    
    # Existing fields
    extracted_account_number = Column(String(100), nullable=True)
    extracted_amount = Column(Float, nullable=True)
    failure_reason = Column(Text, nullable=True)
    gemini_response = Column(Text, nullable=True)
    fraud_score = Column(Integer, default=0)
    fraud_indicators = Column(Text, nullable=True)
    image_hash = Column(String(64), nullable=True)
    
    # Relationships
    enrollment = relationship("Enrollment", back_populates="transactions")
    
    def __repr__(self):
        return f"<Transaction {self.transaction_id} - Status: {self.status.value}>"



class Cart(Base):
    """Cart model - temporary storage for course selection"""
    __tablename__ = "cart"
    
    cart_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.course_id", ondelete="CASCADE"), nullable=False, index=True)
    added_date = Column(DateTime, default=func.now(), nullable=False)
    with_certificate = Column(Boolean, default=False, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="cart_items")
    course = relationship("Course", back_populates="cart_items")
    
    def __repr__(self):
        return f"<Cart {self.cart_id}: User {self.user_id} → Course {self.course_id}>"


# ==================== NEW MODELS ====================

class CourseReview(Base):
    """Course reviews and ratings by students"""
    __tablename__ = 'course_reviews'
    
    review_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey('courses.course_id', ondelete="CASCADE"), nullable=False)
    enrollment_id = Column(Integer, ForeignKey('enrollments.enrollment_id', ondelete="CASCADE"), nullable=False)
    
    rating = Column(Integer, nullable=False)  # 1-5 stars
    comment = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="reviews")
    course = relationship("Course", back_populates="reviews")
    enrollment = relationship("Enrollment", back_populates="review")
    
    def __repr__(self):
        return f"<CourseReview {self.review_id}: Course {self.course_id} - {self.rating}★>"


class NotificationPreference(Base):
    """User notification preferences"""
    __tablename__ = 'notification_preferences'
    
    preference_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete="CASCADE"), nullable=False, unique=True)
    
    # Notification toggles
    course_start_reminder = Column(Boolean, default=True)  # Remind 24h before course starts
    registration_closing_reminder = Column(Boolean, default=True)  # Remind 48h before registration closes
    payment_status_updates = Column(Boolean, default=True)  # Payment approved/rejected
    new_course_announcements = Column(Boolean, default=True)  # New courses available
    broadcast_messages = Column(Boolean, default=True)  # Admin broadcasts
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationship
    user = relationship("User", back_populates="notification_preferences")
    
    def __repr__(self):
        return f"<NotificationPreference User {self.user_id}>"

class InstructorReview(Base):
    """Instructor review model - stores student reviews for instructors"""
    __tablename__ = "instructor_reviews"
    
    review_id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey('courses.course_id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5 stars
    review_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    course = relationship("Course", back_populates="instructor_reviews")
    user = relationship("User", back_populates="instructor_reviews")

class Instructor(Base):
    """Instructor model - stores instructor profiles"""
    __tablename__ = "instructors"
    
    instructor_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    bio = Column(Text, nullable=True)
    specialization = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    photo_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    courses = relationship("Course", back_populates="instructor")
    reviews = relationship("InstructorReview", back_populates="instructor", cascade="all, delete-orphan")
