"""
CRUD operations for database models
"""
from typing import List, Optional, Tuple
from datetime import datetime
from venv import logger
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database.models import (
    CourseReview, NotificationPreference, User, Course, Enrollment, Transaction, Cart,
    PaymentStatus, TransactionStatus
)

# ==================== USER OPERATIONS ====================

def get_or_create_user(session: Session, telegram_user_id: int,
                       username: str = None, first_name: str = None,
                       last_name: str = None, chat_id: int = None) -> User:
    user = session.query(User).filter(User.telegram_user_id == telegram_user_id).first()
    
    if not user:
        user = User(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            telegram_chat_id=chat_id or telegram_user_id
        )
        session.add(user)
        session.flush()
    else:
        if username and user.username != username:
            user.username = username
        if first_name and user.first_name != first_name:
            user.first_name = first_name
        if last_name and user.last_name != last_name:
            user.last_name = last_name
        if chat_id and user.telegram_chat_id != chat_id:
            user.telegram_chat_id = chat_id
            
    return user


def get_user_by_telegram_id(session: Session, telegram_user_id: int) -> Optional[User]:
    return session.query(User).filter(User.telegram_user_id == telegram_user_id).first()

# ==================== COURSE OPERATIONS ====================

def get_all_courses(session: Session) -> List[Course]:
    return session.query(Course).all()

def get_all_active_courses(session: Session) -> List[Course]:
    return session.query(Course).filter(Course.is_active == True).all()

def get_course_by_id(session: Session, course_id: int) -> Optional[Course]:
    return session.query(Course).filter(Course.course_id == course_id).first()

def create_course(session: Session, course_name: str, description: str,
                  price: float, telegram_group_link: str = None,
                  telegram_group_id: int = None, max_students: int = None,
                  start_date: datetime = None, end_date: datetime = None,
                  registration_open_date: datetime = None, 
                  registration_close_date: datetime = None) -> Course:
    course = Course(
        course_name=course_name,
        description=description,
        price=price,
        telegram_group_link=telegram_group_link,
        telegram_group_id=telegram_group_id,
        max_students=max_students,
        start_date=start_date,
        end_date=end_date,
        registration_open_date=registration_open_date,
        registration_close_date=registration_close_date
    )
    session.add(course)
    session.flush()
    return course



def update_course(session: Session, course_id: int, **kwargs) -> Optional[Course]:
    course = get_course_by_id(session, course_id)
    if course:
        for key, value in kwargs.items():
            if hasattr(course, key):
                setattr(course, key, value)
        session.flush()
    return course

# ==================== CART OPERATIONS ====================

def add_to_cart(session: Session, user_id: int, course_id: int) -> Cart:
    existing_cart_item = session.query(Cart).filter(
        and_(Cart.user_id == user_id, Cart.course_id == course_id)
    ).first()
    
    if existing_cart_item:
        return existing_cart_item
    
    cart_item = Cart(user_id=user_id, course_id=course_id)
    session.add(cart_item)
    session.flush()
    return cart_item

def remove_from_cart(session: Session, user_id: int, course_id: int) -> bool:
    cart_item = session.query(Cart).filter(
        and_(Cart.user_id == user_id, Cart.course_id == course_id)
    ).first()
    
    if cart_item:
        session.delete(cart_item)
        session.flush()
        return True
    return False

def get_user_cart(session: Session, user_id: int) -> List[Cart]:
    return session.query(Cart).filter(Cart.user_id == user_id).all()

def clear_user_cart(session: Session, user_id: int):
    session.query(Cart).filter(Cart.user_id == user_id).delete()
    session.flush()

def get_cart_total(session: Session, user_id: int) -> Tuple[int, float]:
    cart_items = get_user_cart(session, user_id)
    count = len(cart_items)
    total = sum(item.course.price for item in cart_items)
    return count, total

def is_course_in_cart(session: Session, user_id: int, course_id: int) -> bool:
    return session.query(Cart).filter(
        and_(Cart.user_id == user_id, Cart.course_id == course_id)
    ).first() is not None

# ==================== ENROLLMENT OPERATIONS ====================

def create_enrollment(session: Session, user_id: int, course_id: int, 
                     payment_amount: float) -> Enrollment:
    enrollment = Enrollment(
        user_id=user_id,
        course_id=course_id,
        payment_amount=payment_amount,
        payment_status=PaymentStatus.PENDING
    )
    session.add(enrollment)
    session.flush()
    return enrollment

def get_user_enrollments(session: Session, user_id: int) -> List[Enrollment]:
    return session.query(Enrollment).filter(Enrollment.user_id == user_id).all()

def get_enrollment_by_id(session: Session, enrollment_id: int) -> Optional[Enrollment]:
    return session.query(Enrollment).filter(Enrollment.enrollment_id == enrollment_id).first()

def update_enrollment_status(session: Session, enrollment_id: int, 
                            status: str, receipt_path: str = None, 
                            admin_notes: str = None) -> Optional[Enrollment]:
    """Update enrollment status - accepts string and converts to enum"""
    enrollment = get_enrollment_by_id(session, enrollment_id)
    
    if enrollment:
        # Convert string status to PaymentStatus enum
        if isinstance(status, str):
            status = status.upper()  # Convert to uppercase
            if status == "VERIFIED":
                enrollment.payment_status = PaymentStatus.VERIFIED
                enrollment.verification_date = datetime.now()
            elif status == "PENDING":
                enrollment.payment_status = PaymentStatus.PENDING
            elif status == "FAILED":
                enrollment.payment_status = PaymentStatus.FAILED
        else:
            enrollment.payment_status = status
            if status == PaymentStatus.VERIFIED:
                enrollment.verification_date = datetime.now()
            
        if receipt_path:
            enrollment.receipt_image_path = receipt_path
        if admin_notes:
            enrollment.admin_notes = admin_notes
            
        session.flush()
    
    return enrollment

def get_user_pending_payments(session: Session, user_id: int) -> List[Enrollment]:
    return session.query(Enrollment).filter(
        and_(
            Enrollment.user_id == user_id,
            or_(
                Enrollment.payment_status == PaymentStatus.PENDING,
                Enrollment.payment_status == PaymentStatus.FAILED
            )
        )
    ).all()

def is_user_enrolled(session: Session, user_id: int, course_id: int) -> bool:
    enrollment = session.query(Enrollment).filter(
        and_(
            Enrollment.user_id == user_id,
            Enrollment.course_id == course_id,
            Enrollment.payment_status == PaymentStatus.VERIFIED
        )
    ).first()
    return enrollment is not None

# ==================== TRANSACTION OPERATIONS ====================

def create_transaction(session: Session, enrollment_id: int, 
                      receipt_image_path: str) -> Transaction:
    transaction = Transaction(
        enrollment_id=enrollment_id,
        receipt_image_path=receipt_image_path,
        status=TransactionStatus.PENDING
    )
    session.add(transaction)
    session.flush()
    return transaction

def update_transaction(session: Session, transaction_id: int, 
                      status: str = None,
                      extracted_account: str = None, 
                      extracted_amount: float = None,
                      failure_reason: str = None, 
                      gemini_response: str = None,
                      admin_id: int = None) -> Optional[Transaction]:
    """Update transaction - accepts string and converts to enum"""
    transaction = session.query(Transaction).filter(
        Transaction.transaction_id == transaction_id
    ).first()
    
    if transaction:
        # Convert string status to TransactionStatus enum
        if status:
            if isinstance(status, str):
                status = status.lower()  # Convert to lowercase for TransactionStatus
                if status == "approved":
                    transaction.status = TransactionStatus.APPROVED
                elif status == "rejected":
                    transaction.status = TransactionStatus.REJECTED
                elif status == "pending":
                    transaction.status = TransactionStatus.PENDING
            else:
                transaction.status = status
                
        if extracted_account:
            transaction.extracted_account_number = extracted_account
        if extracted_amount is not None:
            transaction.extracted_amount = extracted_amount
        if failure_reason:
            transaction.failure_reason = failure_reason
        if gemini_response:
            transaction.gemini_response = gemini_response
        if admin_id:
            transaction.admin_reviewed_by = admin_id
            transaction.admin_review_date = datetime.now()
            
        session.flush()
    
    return transaction

def get_pending_transactions(session: Session) -> List[Transaction]:
    return session.query(Transaction).filter(
        Transaction.status == TransactionStatus.PENDING
    ).order_by(Transaction.submitted_date.desc()).all()

def get_transaction_by_id(session: Session, transaction_id: int) -> Optional[Transaction]:
    return session.query(Transaction).filter(
        Transaction.transaction_id == transaction_id
    ).first()

# ==================== ADMIN/STATS OPERATIONS ====================

def get_enrollment_stats(session: Session) -> dict:
    """Get enrollment statistics with proper enum handling"""
    
    # Count all enrollments
    total_enrollments = session.query(Enrollment).count()
    
    # Count by payment status using enum values properly
    verified_payments = session.query(Enrollment).filter(
        Enrollment.payment_status == PaymentStatus.VERIFIED
    ).count()
    
    pending_payments = session.query(Enrollment).filter(
        Enrollment.payment_status == PaymentStatus.PENDING
    ).count()
    
    failed_payments = session.query(Enrollment).filter(
        Enrollment.payment_status == PaymentStatus.FAILED
    ).count()
    
    # Calculate total revenue from verified payments
    total_revenue = session.query(Enrollment).filter(
        Enrollment.payment_status == PaymentStatus.VERIFIED
    ).with_entities(Enrollment.payment_amount).all()
    
    revenue = sum(float(amount[0]) for amount in total_revenue if amount[0])
    
    # Count pending transactions awaiting admin review
    pending_transactions = session.query(Transaction).filter(
        Transaction.status == TransactionStatus.PENDING
    ).count()
    
    return {
        'total_enrollments': total_enrollments,
        'verified_payments': verified_payments,
        'pending_payments': pending_payments,
        'failed_payments': failed_payments,
        'total_revenue': revenue,
        'pending_transactions': pending_transactions
    }


def get_course_enrollment_count(session: Session, course_id: int) -> int:
    return session.query(Enrollment).filter(
        and_(
            Enrollment.course_id == course_id,
            Enrollment.payment_status == PaymentStatus.VERIFIED
        )
    ).count()

def update_course_group(session: Session, course_id: int, telegram_group_id: str, telegram_group_link: str = None) -> Course:
    """Update course with telegram group information"""
    course = get_course_by_id(session, course_id)
    if course:
        course.telegram_group_id = telegram_group_id
        if telegram_group_link:
            course.telegram_group_link = telegram_group_link
        session.flush()
    return course


def generate_course_invite_link(bot, course: Course) -> str:
    """Generate a single-use invite link for a course group"""
    if not course.telegram_group_id:
        return None
    
    try:
        invite_link = bot.create_chat_invite_link(
            chat_id=int(course.telegram_group_id),
            member_limit=1,
            creates_join_request=True
        )
        return invite_link.invite_link
    except Exception as e:
        logger.error(f"Failed to generate invite link: {e}")
        return None

def get_all_course_enrollment_counts(session: Session) -> dict:
    from sqlalchemy import func
    from .models import Enrollment, PaymentStatus
    
    counts = session.query(
        Enrollment.course_id, 
        func.count(Enrollment.enrollment_id)
    ).filter(
        Enrollment.payment_status == PaymentStatus.VERIFIED
    ).group_by(Enrollment.course_id).all()
    
    return {course_id: count for course_id, count in counts}

def get_daily_verified_enrollments(session: Session, start_date: datetime, end_date: datetime):
    """Get all enrollments verified within a date range"""
    from database.models import Enrollment, PaymentStatus
    from datetime import datetime
    
    return session.query(Enrollment).filter(
        Enrollment.payment_status == PaymentStatus.VERIFIED,
        Enrollment.verification_date >= start_date,
        Enrollment.verification_date < end_date
    ).all()


def get_available_courses_for_registration(session: Session) -> List[Course]:
    """
    Get all active courses where registration is still open
    Filters out courses where:
    - registration_close_date has passed
    - is_active is False
    """
    from datetime import datetime
    import pytz
    
    # Use Sudan time for comparison
    sudan_tz = pytz.timezone('Africa/Khartoum')
    now = datetime.now(sudan_tz).replace(tzinfo=None)  # Remove timezone for DB comparison
    
    courses = session.query(Course).filter(
        Course.is_active == True,
        # Either no close date, or close date is in the future
        or_(
            Course.registration_close_date.is_(None),
            Course.registration_close_date > now
        )
    ).all()
    
    return courses

# ==================== RECEIPT SEARCH OPERATIONS ====================

def get_user_transactions(session: Session, telegram_user_id: int = None, user_id: int = None) -> List[Transaction]:
    """Get all transactions for a specific user"""
    if telegram_user_id:
        user = get_user_by_telegram_id(session, telegram_user_id)
        if not user:
            return []
        user_id = user.user_id
    
    if not user_id:
        return []
    
    # Get all enrollments for this user, then their transactions
    enrollments = session.query(Enrollment).filter(Enrollment.user_id == user_id).all()
    enrollment_ids = [e.enrollment_id for e in enrollments]
    
    if not enrollment_ids:
        return []
    
    transactions = session.query(Transaction).filter(
        Transaction.enrollment_id.in_(enrollment_ids)
    ).order_by(Transaction.submitted_date.desc()).all()
    
    return transactions


def get_transactions_by_date(session: Session, target_date: datetime) -> List[Transaction]:
    """Get all transactions submitted on a specific date"""
    from datetime import timedelta
    
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)
    
    transactions = session.query(Transaction).filter(
        Transaction.submitted_date >= start_of_day,
        Transaction.submitted_date < end_of_day
    ).order_by(Transaction.submitted_date.desc()).all()
    
    return transactions


def get_transactions_by_date_range(session: Session, start_date: datetime, end_date: datetime) -> List[Transaction]:
    """Get all transactions within a date range"""
    from datetime import timedelta
    
    start_of_day = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    transactions = session.query(Transaction).filter(
        Transaction.submitted_date >= start_of_day,
        Transaction.submitted_date <= end_of_day
    ).order_by(Transaction.submitted_date.desc()).all()
    
    return transactions


def get_transactions_by_course(session: Session, course_id: int) -> List[Transaction]:
    """Get all transactions for a specific course"""
    enrollments = session.query(Enrollment).filter(Enrollment.course_id == course_id).all()
    enrollment_ids = [e.enrollment_id for e in enrollments]
    
    if not enrollment_ids:
        return []
    
    transactions = session.query(Transaction).filter(
        Transaction.enrollment_id.in_(enrollment_ids)
    ).order_by(Transaction.submitted_date.desc()).all()
    
    return transactions


def get_transactions_by_status(session: Session, status: TransactionStatus) -> List[Transaction]:
    """Get all transactions with a specific status"""
    transactions = session.query(Transaction).filter(
        Transaction.status == status
    ).order_by(Transaction.submitted_date.desc()).all()
    
    return transactions


# ==================== COURSE REVIEW OPERATIONS ====================

def create_review(session: Session, user_id: int, course_id: int, 
                  enrollment_id: int, rating: int, comment: str = None):
    """Create a course review"""
    review = CourseReview(
        user_id=user_id,
        course_id=course_id,
        enrollment_id=enrollment_id,
        rating=rating,
        comment=comment
    )
    session.add(review)
    session.flush()
    return review


def get_course_reviews(session: Session, course_id: int) -> List:
    """Get all reviews for a course"""
    return session.query(CourseReview).filter(
        CourseReview.course_id == course_id
    ).order_by(CourseReview.created_at.desc()).all()


def get_user_review_for_course(session: Session, user_id: int, course_id: int):
    """Check if user already reviewed a course"""
    return session.query(CourseReview).filter(
        CourseReview.user_id == user_id,
        CourseReview.course_id == course_id
    ).first()


def get_course_average_rating(session: Session, course_id: int) -> float:
    """Get average rating for a course"""
    from sqlalchemy import func
    result = session.query(func.avg(CourseReview.rating)).filter(
        CourseReview.course_id == course_id
    ).scalar()
    return round(result, 1) if result else 0.0


def get_course_review_count(session: Session, course_id: int) -> int:
    """Get total number of reviews for a course"""
    return session.query(CourseReview).filter(
        CourseReview.course_id == course_id
    ).count()


# ==================== NOTIFICATION PREFERENCE OPERATIONS ====================

def get_or_create_notification_preferences(session: Session, user_id: int):
    """Get user's notification preferences or create default ones"""
    prefs = session.query(NotificationPreference).filter(
        NotificationPreference.user_id == user_id
    ).first()
    
    if not prefs:
        prefs = NotificationPreference(user_id=user_id)
        session.add(prefs)
        session.flush()
    
    return prefs


def update_notification_preference(session: Session, user_id: int, 
                                   preference_name: str, value: bool):
    """Update a specific notification preference"""
    prefs = get_or_create_notification_preferences(session, user_id)
    setattr(prefs, preference_name, value)
    session.flush()
    return prefs


# ==================== SEARCH OPERATIONS ====================

def search_students(session: Session, query: str) -> List[User]:
    """Search for students by name or username"""
    from sqlalchemy import or_, func
    
    search_term = f"%{query.lower()}%"
    
    students = session.query(User).filter(
        or_(
            func.lower(User.first_name).like(search_term),
            func.lower(User.last_name).like(search_term),
            func.lower(User.username).like(search_term)
        )
    ).all()
    
    return students


# ==================== ENROLLMENT OPERATIONS (for reviews) ====================

def get_completed_enrollments_without_review(session: Session) -> List[Enrollment]:
    """Get enrollments for completed courses that haven't been reviewed yet"""
    from datetime import datetime
    import pytz
    
    sudan_tz = pytz.timezone('Africa/Khartoum')
    now = datetime.now(sudan_tz).replace(tzinfo=None)
    
    # Get verified enrollments for courses that have ended
    enrollments = session.query(Enrollment).join(Course).outerjoin(CourseReview).filter(
        Enrollment.payment_status == PaymentStatus.VERIFIED,
        Course.end_date.isnot(None),
        Course.end_date < now,
        CourseReview.review_id.is_(None)  # No review yet
    ).all()
    
    return enrollments


# ==================== BROADCAST OPERATIONS ====================

def get_all_active_students(session: Session) -> List[User]:
    """Get all users with at least one verified enrollment"""
    from sqlalchemy import distinct
    
    student_ids = session.query(distinct(Enrollment.user_id)).filter(
        Enrollment.payment_status == PaymentStatus.VERIFIED
    ).all()
    
    student_ids = [sid[0] for sid in student_ids]
    
    students = session.query(User).filter(User.user_id.in_(student_ids)).all()
    return students


def get_course_students(session: Session, course_id: int) -> List[User]:
    """Get all verified students enrolled in a specific course"""
    enrollments = session.query(Enrollment).filter(
        Enrollment.course_id == course_id,
        Enrollment.payment_status == PaymentStatus.VERIFIED
    ).all()
    
    user_ids = [e.user_id for e in enrollments]
    students = session.query(User).filter(User.user_id.in_(user_ids)).all()
    return students

# ==================== SEARCH OPERATIONS ====================

def search_students(session: Session, query: str) -> List[User]:
    """Search for students by name or username"""
    from sqlalchemy import or_, func
    
    search_term = f"%{query.lower()}%"
    
    students = session.query(User).filter(
        or_(
            func.lower(User.first_name).like(search_term),
            func.lower(User.last_name).like(search_term),
            func.lower(User.username).like(search_term)
        )
    ).all()
    
    return students

def update_enrollment_partial_payment(session: Session, enrollment_id: int, amount_paid: float, receipt_path: str = None):
    """Update enrollment with partial payment"""
    from database.models import Enrollment, PaymentStatus
    
    enrollment = session.query(Enrollment).filter(Enrollment.enrollment_id == enrollment_id).first()
    
    if enrollment:
        # Add to existing amount_paid
        enrollment.amount_paid += amount_paid
        
        # Keep status as PENDING until full amount is paid
        enrollment.payment_status = PaymentStatus.PENDING
        
        if receipt_path:
            enrollment.receipt_image_path = receipt_path
        
        session.commit()
        session.refresh(enrollment)
    
    return enrollment

def update_user_legal_name(
    session: Session, 
    user_id: int, 
    legal_name_first: str,
    legal_name_father: str,
    legal_name_grandfather: str,
    legal_name_great_grandfather: str
) -> bool:
    """
    Update user's legal name (4 parts)
    
    Args:
        session: Database session
        user_id: User ID
        legal_name_first: First name
        legal_name_father: Father's name
        legal_name_grandfather: Grandfather's name
        legal_name_great_grandfather: Great grandfather's name
    
    Returns:
        bool: True if updated successfully
    """
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            return False
        
        user.legal_name_first = legal_name_first.strip()
        user.legal_name_father = legal_name_father.strip()
        user.legal_name_grandfather = legal_name_grandfather.strip()
        user.legal_name_great_grandfather = legal_name_great_grandfather.strip()
        
        session.commit()
        logger.info(f"Updated legal name for user {user_id}")
        return True
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating legal name for user {user_id}: {e}")
        return False


def get_user_legal_name(session: Session, user_id: int) -> Optional[str]:
    """
    Get user's full legal name (all 4 parts combined)
    
    Returns:
        str: Full legal name or None if not set
    """
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            return None
        
        # Check if legal name is set
        if not user.legal_name_first:
            return None
        
        # Combine all parts
        name_parts = [
            user.legal_name_first,
            user.legal_name_father,
            user.legal_name_grandfather,
            user.legal_name_great_grandfather
        ]
        
        return " ".join(filter(None, name_parts))
        
    except Exception as e:
        logger.error(f"Error getting legal name for user {user_id}: {e}")
        return None
