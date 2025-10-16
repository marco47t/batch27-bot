"""
Course selection and cart management handlers
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import crud, get_db
from database.models import PaymentStatus
from utils.keyboards import (
    course_selection_keyboard, 
    cart_keyboard, 
    back_to_main_keyboard,
    courses_menu_keyboard
)
from utils.messages import (
    course_list_message, 
    cart_message, 
    error_message,
    course_detail_message
)
from utils.helpers import log_user_action
from config import CallbackPrefix
import logging

logger = logging.getLogger(__name__)

async def course_selection_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available courses for selection - EXCLUDING already enrolled courses"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    telegram_user_id = user.id
    
    logger.info(f"User {telegram_user_id} accessing course selection menu")
    
    with get_db() as session:
        # ENSURE USER EXISTS FIRST
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        session.flush()
        session.commit()
        
        # USE INTERNAL USER ID
        internal_user_id = db_user.user_id
        logger.info(f"User {telegram_user_id} has internal ID: {internal_user_id}")
        
        # Get ALL courses
        all_courses = crud.get_available_courses_for_registration(session)

        
        # Get user's enrollments (all statuses) - USE INTERNAL ID
        user_enrollments = crud.get_user_enrollments(session, internal_user_id)
        enrolled_course_ids = [e.course_id for e in user_enrollments]
        
        # Filter out already enrolled courses
        available_courses = [c for c in all_courses if c.course_id not in enrolled_course_ids]
        
        # Get cart items - USE INTERNAL ID
        cart_items = crud.get_user_cart(session, internal_user_id)
        cart_course_ids = [item.course_id for item in cart_items]
        
        # Get enrollment counts for capacity checking
        course_enrollment_counts = {}
        for course in available_courses:
            enrollment_count = session.query(crud.Enrollment).filter(
                crud.Enrollment.course_id == course.course_id,
                crud.Enrollment.payment_status == PaymentStatus.VERIFIED
            ).count()
            course_enrollment_counts[course.course_id] = enrollment_count
    
    if not available_courses:
        await query.edit_message_text(
            "✅ أنت مسجل في جميع الدورات المتاحة!",
            reply_markup=back_to_main_keyboard()
        )
        return
    
    logger.info(f"Showing {len(available_courses)} available courses for user {telegram_user_id} (cart has {len(cart_items)} items)")
    
    cart_total = sum(course.price for course in available_courses if course.course_id in cart_course_ids)

    await query.edit_message_text(
        course_list_message(available_courses, course_enrollment_counts),
        reply_markup=course_selection_keyboard(available_courses, cart_course_ids, cart_total)
    )



async def course_details_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show course details menu"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    logger.info(f"User {user_id} accessing course details menu")
    
    with get_db() as session:
        courses = crud.get_all_courses(session)
    
    keyboard = []
    for course in courses:
        keyboard.append([
            InlineKeyboardButton(
                f"📖 {course.course_name}", 
                callback_data=f"{CallbackPrefix.COURSE_DETAIL}{course.course_id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("→ عودة", callback_data=CallbackPrefix.BACK_COURSES)])
    
    await query.edit_message_text(
        "📚 اختر دورة لعرض التفاصيل:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def course_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed information about a specific course"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    course_id = int(query.data[len(CallbackPrefix.COURSE_DETAIL):])
    logger.info(f"User {user_id} viewing details for course {course_id}")
    
    with get_db() as session:
        course = crud.get_course_by_id(session, course_id)
        
        if not course:
            logger.warning(f"Course {course_id} not found for user {user_id}")
            await query.edit_message_text(
                error_message("course_not_found"),
                reply_markup=back_to_main_keyboard()
            )
            return
        
        # Get enrollment count
        enrollment_count = session.query(crud.Enrollment).filter(
            crud.Enrollment.course_id == course.course_id,
            crud.Enrollment.payment_status == PaymentStatus.VERIFIED
        ).count()
    
    keyboard = [
        [InlineKeyboardButton("→ عودة لقائمة الدورات", callback_data="course_details_menu")],
        [InlineKeyboardButton("→ العودة للقائمة الرئيسية", callback_data=CallbackPrefix.BACK_MAIN)]
    ]
    
    await query.edit_message_text(
        course_detail_message(course, enrollment_count),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def course_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle course selection - Add to cart"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    telegram_user_id = user.id  # This is the Telegram ID (919340565)
    course_id = int(query.data.split('_')[2])
    
    logger.info(f"User {telegram_user_id} attempting to select course {course_id}")
    
    with get_db() as session:
        # ENSURE USER EXISTS IN DATABASE FIRST
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        session.flush()
        session.commit()
        session.refresh(db_user)
        
        # GET INTERNAL USER ID (not telegram_user_id!)
        internal_user_id = db_user.user_id  # This is the internal ID (1)
        logger.info(f"User {telegram_user_id} has internal ID: {internal_user_id}")
        
        course = crud.get_course_by_id(session, course_id)
        
        if not course:
            logger.warning(f"Course {course_id} not found")
            await query.edit_message_text("❌ الدورة غير موجودة.")
            return
        
        logger.info(f"Course {course_id} found: {course.course_name}")
        from datetime import datetime
        import pytz

        # Use Sudan timezone for date comparison
        sudan_tz = pytz.timezone('Africa/Khartoum')
        now = datetime.now(sudan_tz).replace(tzinfo=None)

        if course.registration_close_date and now > course.registration_close_date:
            await query.answer(
                "❌ عذراً، التسجيل في هذه الدورة مغلق\n"
                "Registration for this course is closed",
                show_alert=True
            )
            return 

        if course.registration_open_date and now < course.registration_open_date:
            await query.answer(
                f"⏰ التسجيل سيفتح في: {course.registration_open_date.strftime('%Y-%m-%d')}\n"
                f"Registration opens on: {course.registration_open_date.strftime('%Y-%m-%d')}",
                show_alert=True
            )
            return
        # Check if already enrolled - use internal_user_id
        if crud.is_user_enrolled(session, internal_user_id, course_id):
            logger.info(f"User {telegram_user_id} already enrolled in course {course_id}")
            await query.answer("⚠️ أنت مسجل بالفعل في هذه الدورة!", show_alert=True)
            return
        
        logger.info(f"User {telegram_user_id} not enrolled, checking cart...")
        
        # Check if already in cart - use internal_user_id  
        if crud.is_course_in_cart(session, internal_user_id, course_id):
            logger.info(f"Course {course_id} already in cart for user {telegram_user_id}")
            await query.answer("⚠️ هذه الدورة موجودة بالفعل في السلة!", show_alert=True)
            return
        
        logger.info(f"Course {course_id} not in cart, adding now...")
        
        # Add to cart - use internal_user_id
        try:
            cart_item = crud.add_to_cart(session, internal_user_id, course_id)
            session.commit()
            logger.info(f"✅ Successfully added course {course_id} to cart for user {telegram_user_id} (internal ID: {internal_user_id}), cart_id={cart_item.cart_id}")
        except Exception as e:
            logger.error(f"❌ Error adding to cart: {e}")
            session.rollback()
            await query.answer("❌ حدث خطأ أثناء إضافة الدورة للسلة", show_alert=True)
            return
        
        await query.answer("✅ تمت إضافة الدورة إلى السلة!", show_alert=True)
        logger.info(f"Showing success message to user {telegram_user_id}")
        
        # Show updated courses list with refreshed data - use internal_user_id
        user_enrollments = crud.get_user_enrollments(session, internal_user_id)
        enrolled_course_ids = [e.course_id for e in user_enrollments]
        
        all_courses = crud.get_available_courses_for_registration(session)
        available_courses = [c for c in all_courses if c.course_id not in enrolled_course_ids]
        
        cart_items = crud.get_user_cart(session, internal_user_id)
        cart_course_ids = [item.course_id for item in cart_items]
        
        logger.info(f"Cart now has {len(cart_items)} items for user {telegram_user_id}")
        
        # Get enrollment counts
        course_enrollment_counts = {}
        for c in available_courses:
            count = session.query(crud.Enrollment).filter(
                crud.Enrollment.course_id == c.course_id,
                crud.Enrollment.payment_status == PaymentStatus.VERIFIED
            ).count()
            course_enrollment_counts[c.course_id] = count
    
    # Calculate cart total
    cart_total = sum(c.price for c in available_courses if c.course_id in cart_course_ids)

    await query.edit_message_text(
        course_list_message(available_courses, course_enrollment_counts),
        reply_markup=course_selection_keyboard(available_courses, cart_course_ids, cart_total)
    )

    
    logger.info(f"Updated message sent to user {telegram_user_id}")



async def course_deselect_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove course from cart"""
    query = update.callback_query
    telegram_user_id = query.from_user.id
    
    course_id = int(query.data[len(CallbackPrefix.COURSE_DESELECT):])
    logger.info(f"User {telegram_user_id} removing course {course_id} from cart")
    
    with get_db() as session:
        # Get user with internal ID
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=telegram_user_id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )
        session.flush()
        
        internal_user_id = db_user.user_id
        
        course = crud.get_course_by_id(session, course_id)
        
        if not course:
            await query.answer("❌ Course not found!", show_alert=True)
            return
        
        crud.remove_from_cart(session, internal_user_id, course_id)
        session.commit()
        
        # Get updated data using internal ID
        user_enrollments = crud.get_user_enrollments(session, internal_user_id)
        enrolled_course_ids = [e.course_id for e in user_enrollments]
        
        all_courses = crud.get_all_courses(session)
        available_courses = [c for c in all_courses if c.course_id not in enrolled_course_ids]
        
        cart_items = crud.get_user_cart(session, internal_user_id)
        cart_course_ids = [item.course_id for item in cart_items]
        
        # Get enrollment counts
        course_enrollment_counts = {}
        for c in available_courses:
            count = session.query(crud.Enrollment).filter(
                crud.Enrollment.course_id == c.course_id,
                crud.Enrollment.payment_status == PaymentStatus.VERIFIED
            ).count()
            course_enrollment_counts[c.course_id] = count
    
    await query.answer(f"🗑️ تمت إزالة {course.course_name} من السلة!")
    logger.info(f"User {telegram_user_id} removed course {course_id} from cart")
    log_user_action(telegram_user_id, "course_deselected", f"course_id={course_id}")
    
    cart_total = sum(course.price for course in available_courses if course.course_id in cart_course_ids)

# Calculate cart total
    cart_total = sum(c.price for c in available_courses if c.course_id in cart_course_ids)

    await query.edit_message_text(
        course_list_message(available_courses, course_enrollment_counts),
        reply_markup=course_selection_keyboard(available_courses, cart_course_ids, cart_total)
    )



async def view_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View shopping cart"""
    query = update.callback_query
    await query.answer()
    telegram_user_id = query.from_user.id
    
    logger.info(f"User {telegram_user_id} viewing cart")
    
    with get_db() as session:
        # Get user with internal ID
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=telegram_user_id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )
        session.flush()
        
        internal_user_id = db_user.user_id
        
        # Get cart using internal ID
        cart_items = crud.get_user_cart(session, internal_user_id)
        
        if not cart_items:
            logger.info(f"Cart is empty for user {telegram_user_id}")
            await query.edit_message_text(
                "🛒 سلة التسوق فارغة\n\nقم بإضافة دورات من قائمة التسجيل.",
                reply_markup=courses_menu_keyboard()
            )
            return
        
        courses = [item.course for item in cart_items]
        total = sum(course.price for course in courses)
    
    logger.info(f"User {telegram_user_id} cart: {len(cart_items)} items, total={total}")
    
    await query.edit_message_text(
        cart_message(courses, total),
        reply_markup=cart_keyboard()
    )


async def confirm_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm cart and create pending enrollments"""
    query = update.callback_query
    await query.answer()
    telegram_user_id = query.from_user.id
    
    logger.info(f"User {telegram_user_id} confirming cart")
    
    with get_db() as session:
        # Get user with internal ID
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=telegram_user_id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )
        session.flush()
        
        internal_user_id = db_user.user_id
        
        # Get cart using internal ID
        cart_items = crud.get_user_cart(session, internal_user_id)
        
        if not cart_items:
            logger.warning(f"User {telegram_user_id} tried to confirm empty cart")
            await query.edit_message_text(
                error_message("cart_empty"),
                reply_markup=back_to_main_keyboard()
            )
            return
        
        courses = [item.course for item in cart_items]
        total = sum(course.price for course in courses)
        
        # Create pending enrollments using internal ID
        enrollment_ids = []
        for course in courses:
            enrollment = crud.create_enrollment(session, internal_user_id, course.course_id, course.price)
            enrollment_ids.append(enrollment.enrollment_id)
            logger.info(f"Created enrollment {enrollment.enrollment_id} for user {telegram_user_id}, course {course.course_id}")
        
        session.commit()
    
    # Store in context for payment flow
    context.user_data["cart_total_for_payment"] = total
    context.user_data["pending_enrollment_ids_for_payment"] = enrollment_ids
    
    logger.info(f"User {telegram_user_id} cart confirmed: {len(enrollment_ids)} enrollments, total={total}")
    log_user_action(telegram_user_id, "cart_confirmed", f"total={total}, enrollments={enrollment_ids}")
    
    # Import here to avoid circular import
    from handlers.payment_handlers import proceed_to_payment_callback
    await proceed_to_payment_callback(update, context)


async def clear_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear all items from cart"""
    query = update.callback_query
    await query.answer()
    telegram_user_id = query.from_user.id
    
    logger.info(f"User {telegram_user_id} clearing cart")
    
    with get_db() as session:
        # Get user with internal ID
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=telegram_user_id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )
        session.flush()
        
        internal_user_id = db_user.user_id
        
        # Clear cart using internal ID
        crud.clear_user_cart(session, internal_user_id)
        session.commit()
    
    logger.info(f"Cart cleared for user {telegram_user_id}")
    log_user_action(telegram_user_id, "cart_cleared", "")
    
    await query.edit_message_text(
        "🗑️ تم تفريغ السلة",
        reply_markup=courses_menu_keyboard()
    )