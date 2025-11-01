"""
Course selection and cart management handlers
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import crud, get_db
from database.models import Course, PaymentStatus
from utils.keyboards import (
    certificate_option_keyboard,
    course_selection_keyboard, 
    cart_keyboard, 
    back_to_main_keyboard,
    courses_menu_keyboard
)
from utils.messages import (
    course_instructor_details,
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
    
    courses_per_page = 5
    page = 0
    if query.data.startswith('course_selection_page_'):
        page = int(query.data.split('_')[-1])

    logger.info(f"User {telegram_user_id} accessing course selection menu, page {page}")
    
    with get_db() as session:
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        session.flush()
        session.commit()
        
        internal_user_id = db_user.user_id
        
        all_courses = crud.get_available_courses_for_registration(session)
        user_enrollments = crud.get_user_enrollments(session, internal_user_id)
        enrolled_course_ids = [e.course_id for e in user_enrollments]
        
        available_courses = [c for c in all_courses if c.course_id not in enrolled_course_ids]
        available_courses.sort(key=lambda c: c.course_name)

        cart_items = crud.get_user_cart(session, internal_user_id)
        cart_course_ids = [item.course_id for item in cart_items]
        
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

    total_pages = (len(available_courses) + courses_per_page - 1) // courses_per_page
    start = page * courses_per_page
    end = start + courses_per_page
    paginated_courses = available_courses[start:end]

    cart_totals = crud.calculate_cart_total(session, internal_user_id)
    cart_total = cart_totals['total']
    
    await query.edit_message_text(
        course_list_message(paginated_courses, course_enrollment_counts),
        reply_markup=course_selection_keyboard(
            paginated_courses, 
            cart_course_ids, 
            cart_total,
            page=page,
            total_pages=total_pages
        )
    )



async def course_details_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show course details menu with pagination"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Determine page number
    page = 0
    if query.data.startswith('course_details_page_'):
        page = int(query.data.split('_')[-1])

    logger.info(f"User {user_id} accessing course details menu, page {page}")

    with get_db() as session:
        courses = crud.get_all_courses(session)
    
    # Sort courses alphabetically
    courses.sort(key=lambda c: c.course_name)

    # Use the existing paginated keyboard
    from utils.keyboards import course_details_keyboard
    paginated_keyboard = course_details_keyboard(courses, page=page)

    await query.edit_message_text(
        "📚 اختر دورة لعرض التفاصيل:",
        reply_markup=paginated_keyboard
    )


async def course_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show BRIEF course summary with button menu (UPDATED)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    course_id = int(query.data[len(CallbackPrefix.COURSE_DETAIL):])
    
    logger.info(f"User {user_id} viewing details for course {course_id}")
    
    with get_db() as session:
        courses = crud.get_all_courses(session)
        courses.sort(key=lambda c: c.course_name) # Ensure consistent order
        
        course = next((c for c in courses if c.course_id == course_id), None)
        
        if not course:
            logger.warning(f"Course {course_id} not found for user {user_id}")
            await query.edit_message_text(
                error_message("course_not_found"),
                reply_markup=back_to_main_keyboard()
            )
            return
        
        current_course_index = courses.index(course)
        
        # Get enrollment count
        enrollment_count = session.query(crud.Enrollment).filter(
            crud.Enrollment.course_id == course.course_id,
            crud.Enrollment.payment_status == PaymentStatus.VERIFIED
        ).count()
        
        # Import the new functions
        from utils.messages import course_summary_message
        from utils.keyboards import course_info_buttons_keyboard
        
        # Show BRIEF summary instead of full details
        await query.edit_message_text(
            course_summary_message(course, enrollment_count),
            reply_markup=course_info_buttons_keyboard(course_id, courses, current_course_index),
            parse_mode='Markdown'
        )


# ADD these 2 NEW handlers after course_detail_callback:

async def course_description_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show course description details"""
    query = update.callback_query
    await query.answer()
    
    course_id = int(query.data.split('_')[-1])
    
    with get_db() as session:
        courses = crud.get_all_courses(session)
        courses.sort(key=lambda c: c.course_name)
        
        course = next((c for c in courses if c.course_id == course_id), None)
        
        if not course:
            await query.edit_message_text("❌ الدورة غير موجودة.")
            return
            
        current_course_index = courses.index(course)
        
        from utils.messages import course_description_details
        from utils.keyboards import course_info_buttons_keyboard
        
        message = course_description_details(course, session)
        
        await query.edit_message_text(
            message,
            reply_markup=course_info_buttons_keyboard(course_id, courses, current_course_index),
            parse_mode='Markdown'
        )




async def course_dates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show course dates and schedule"""
    query = update.callback_query
    await query.answer()
    
    course_id = int(query.data.split('_')[-1])
    
    with get_db() as session:
        courses = crud.get_all_courses(session)
        courses.sort(key=lambda c: c.course_name)
        
        course = next((c for c in courses if c.course_id == course_id), None)
        
        if not course:
            await query.edit_message_text("❌ الدورة غير موجودة.")
            return
            
        current_course_index = courses.index(course)
        
        from utils.messages import course_dates_details
        from utils.keyboards import course_info_buttons_keyboard
        
        await query.edit_message_text(
            course_dates_details(course),
            reply_markup=course_info_buttons_keyboard(course_id, courses, current_course_index),
            parse_mode='Markdown'
        )


async def course_instructor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show instructor details with ratings"""
    query = update.callback_query
    await query.answer()
    
    course_id = int(query.data.split('_')[-1])
    
    with get_db() as session:
        course = crud.get_course_by_id(session, course_id)
        
        if not course:
            await query.edit_message_text("❌ الدورة غير موجودة.")
            return
        
        # FIX: Use plain text instead of Markdown if instructor details has special characters
        message = course_instructor_details(course, session)
        
        # Build keyboard with rate button if instructor exists
        keyboard_buttons = []
        
        if course.instructor:
            # Add rate instructor button
            keyboard_buttons.append([InlineKeyboardButton(
                "⭐ قيّم المدرب | Rate Instructor",
                callback_data=f"start_rate_{course.instructor.instructor_id}"
            )])
        
        # Add back buttons
        keyboard_buttons.extend([
            [InlineKeyboardButton("🔙 عودة | Back", callback_data=f"course_detail_{course_id}")],
            [InlineKeyboardButton("→ العودة للقائمة الرئيسية", callback_data=CallbackPrefix.BACK_MAIN)]
        ])
        
        try:
            # Try with Markdown first
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard_buttons),
                parse_mode='Markdown'
            )
        except Exception as e:
            # If Markdown fails, send without parse_mode
            logger.error(f"Markdown parsing error for instructor details: {e}")
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard_buttons),
                parse_mode=None  # NO FORMATTING
            )



async def register_course_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle registration from the course details view."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    telegram_user_id = user.id
    course_id = int(query.data.split('_')[-1])

    logger.info(f"User {telegram_user_id} attempting to register for course {course_id} from details view")

    with get_db() as session:
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

        internal_user_id = db_user.user_id
        course = crud.get_course_by_id(session, course_id)

        if not course:
            await query.edit_message_text("❌ الدورة غير موجودة.")
            return

        if crud.is_user_enrolled(session, internal_user_id, course_id):
            await query.answer("⚠️ أنت مسجل بالفعل في هذه الدورة!", show_alert=True)
            return

        if course.certificate_available and course.certificate_price > 0:
            message = f"""
            📚 <b>{course.course_name}</b>
    
            💰 سعر الدورة: {course.price:.0f} SDG
            📜 سعر الشهادة: {course.certificate_price:.0f} SDG
    
            هل تريد التسجيل مع شهادة؟
            Do you want to register with a certificate?
            """
            await query.edit_message_text(
                message,
                reply_markup=certificate_option_keyboard(course_id, register_flow=True),
                parse_mode='HTML'
            )
            return
        else:
            # No certificate, proceed directly to payment
            payment_amount = course.price
            enrollment = crud.create_enrollment(session, internal_user_id, course.course_id, payment_amount)
            enrollment.with_certificate = False # Explicitly set to False
            session.commit()

            context.user_data['cart_total_for_payment'] = payment_amount
            context.user_data['pending_enrollment_ids_for_payment'] = [enrollment.enrollment_id]
            context.user_data['awaiting_receipt_upload'] = True
            context.user_data['expected_amount_for_gemini'] = payment_amount

            from handlers.payment_handlers import proceed_to_payment_callback
            await proceed_to_payment_callback(update, context)



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
        if course.certificate_available and course.certificate_price > 0:
            # Ask user if they want certificate
            message = f"""
        📚 <b>{course.course_name}</b>

        💰 سعر الدورة: {course.price:.0f} SDG
        📜 سعر الشهادة: {course.certificate_price:.0f} SDG

        هل تريد التسجيل مع شهادة؟
        Do you want to register with a certificate?
        """
            await query.edit_message_text(
                message,
                reply_markup=certificate_option_keyboard(course_id),
                parse_mode='HTML'
            )
            return  # ← Stop here, wait for certificate choice
        else:
            # No certificate available, add directly to cart (old behavior)
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
    cart_totals = crud.calculate_cart_total(session, internal_user_id)
    cart_total = cart_totals['total']
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
        
        all_courses = crud.get_available_courses_for_registration(session)
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
        
        # ✅ CALCULATE CART TOTAL INSIDE SESSION BLOCK
        cart_totals = crud.calculate_cart_total(session, internal_user_id)
        cart_total = cart_totals['total']
    
    # ✅ NOW OUTSIDE SESSION - answer and edit message
    await query.answer(f"[translate:🗑️ تمت إزالة {course.course_name} من السلة!]")
    logger.info(f"User {telegram_user_id} removed course {course_id} from cart")
    log_user_action(telegram_user_id, "course_deselected", f"course_id={course_id}")
    
    await query.edit_message_text(
        course_list_message(available_courses, course_enrollment_counts),
        reply_markup=course_selection_keyboard(available_courses, cart_course_ids, cart_total)
    )

async def view_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View shopping cart with pending courses showing remaining balance"""
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
        
        # ✅ ALSO GET PENDING ENROLLMENTS WITH PARTIAL PAYMENTS
        pending_enrollments = session.query(crud.Enrollment).filter(
            crud.Enrollment.user_id == internal_user_id,
            crud.Enrollment.payment_status == PaymentStatus.PENDING
        ).all()
        
        if not cart_items and not pending_enrollments:
            logger.info(f"Cart is empty for user {telegram_user_id}")
            await query.edit_message_text(
                "[translate:سلة التسوق فارغة]\n\n[translate:قم بإضافة دورات من قائمة التسجيل]",
                reply_markup=courses_menu_keyboard()
            )
            return
        
        # ✅ BUILD TOTAL WITH BOTH CART ITEMS AND PENDING BALANCES
        cart_totals = crud.calculate_cart_total(session, internal_user_id)

        # Build cart message with certificate info
        cart_text = "🛒 سلة التسوق / Shopping Cart\n\n"

        for item in cart_items:
            course = item.course
            cert_icon = "📜" if item.with_certificate else ""
            cert_text = "\n   ✅ مع شهادة (With Certificate)" if item.with_certificate else ""
            
            item_price = course.price
            if item.with_certificate and course.certificate_available:
                item_price += course.certificate_price
            
            cart_text += f"{cert_icon} {course.course_name}\n"
            cart_text += f"   💰 {item_price:.0f} SDG{cert_text}\n\n"

        cart_text += f"━━━━━━━━━━━━━━\n"
        cart_text += f"📚 الدورات: {cart_totals['course_price']:.0f} SDG\n"
        cart_text += f"📜 الشهادات: {cart_totals['certificate_price']:.0f} SDG\n"
        cart_text += f"━━━━━━━━━━━━━━\n"
        cart_text += f"💵 الإجمالي: {cart_totals['total']:.0f} SDG"

        total = cart_totals['total']
        
        # Add remaining balances from pending enrollments
        for enrollment in pending_enrollments:
            paid = enrollment.amount_paid or 0
            remaining = enrollment.payment_amount - paid
            if remaining > 0:
                total += remaining
        
        # ✅ PASS PENDING ENROLLMENTS TO MESSAGE FUNCTION
        await query.edit_message_text(
            cart_text,  # We already built this above
            reply_markup=cart_keyboard(),
            parse_mode='Markdown'
        )
        
        logger.info(f"User {telegram_user_id} cart: {len(cart_items)} new items + {len(pending_enrollments)} pending, total={total:.0f}")
        



async def confirm_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm cart and check legal name before proceeding to payment"""
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
        
        # Check if user has legal name registered
        if not crud.has_legal_name(session, internal_user_id):
            logger.info(f"User {telegram_user_id} needs to provide legal name first")
            
            await query.edit_message_text(
                "📝 *تسجيل الاسم القانوني مطلوب | Legal Name Required*\n\n"
                "قبل إتمام التسجيل، نحتاج إلى اسمك الرباعي الكامل كما هو مكتوب في المستندات الرسمية.\n"
                "Before completing registration, we need your full four-part name as written on official documents.\n\n"
                "⚠️ *مهم جداً | Very Important:*\n"
                "• يجب أن يكون الاسم باللغة الإنجليزية\n"
                "• Must be in English\n"
                "• الاسم الرباعي: (اسمك - اسم والدك - اسم جدك - اسم جد والدك)\n"
                "• Four parts: (Your name - Father - Grandfather - Great-grandfather)\n\n"
                "🔹 *الخطوة 1/4:* أدخل اسمك الأول\n"
                "🔹 *Step 1/4:* Enter your first name",
                parse_mode='Markdown'
            )
            
            # Set context for legal name collection during registration
            context.user_data['collecting_legal_name_for_registration'] = True
            context.user_data['registration_internal_user_id'] = internal_user_id
            
            return  # Stop here, wait for legal name input
        
        # User has legal name, proceed with normal cart confirmation
        cart_items = crud.get_user_cart(session, internal_user_id)
        
        if not cart_items:
            logger.warning(f"User {telegram_user_id} tried to confirm empty cart")
            await query.edit_message_text(
                error_message("cart_empty"),
                reply_markup=back_to_main_keyboard()
            )
            return
        
        # ✅ Calculate total with certificates
        cart_totals = crud.calculate_cart_total(session, internal_user_id)
        total = cart_totals['total']
        
        # Create pending enrollments using internal ID
        enrollment_ids = []
        for item in cart_items:
            course = item.course
            
            # Calculate payment amount including certificate
            payment_amount = course.price
            if item.with_certificate and course.certificate_available:
                payment_amount += course.certificate_price
            
            # CHECK IF PENDING ENROLLMENT ALREADY EXISTS
            existing_enrollment = session.query(crud.Enrollment).filter(
                crud.Enrollment.user_id == internal_user_id,
                crud.Enrollment.course_id == course.course_id,
                crud.Enrollment.payment_status == PaymentStatus.PENDING
            ).first()
            
            if existing_enrollment:
                # Update existing enrollment with correct amount and certificate flag
                existing_enrollment.payment_amount = payment_amount
                existing_enrollment.with_certificate = item.with_certificate
                enrollment_ids.append(existing_enrollment.enrollment_id)
                logger.info(f"Reusing existing pending enrollment {existing_enrollment.enrollment_id}, amount: {payment_amount}")
            else:
                # Create new enrollment with certificate info
                enrollment = crud.create_enrollment(session, internal_user_id, course.course_id, payment_amount)
                enrollment.with_certificate = item.with_certificate
                enrollment_ids.append(enrollment.enrollment_id)
                logger.info(f"Created NEW enrollment {enrollment.enrollment_id}, amount: {payment_amount}, with_cert: {item.with_certificate}")

        session.commit()

        # ✅ CLEAR CART AFTER CONFIRMATION
        crud.clear_user_cart(session, internal_user_id)
        session.commit()
        
        # Store in context for payment flow
        context.user_data['cart_total_for_payment'] = total
        context.user_data['pending_enrollment_ids_for_payment'] = enrollment_ids
        
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

async def handle_legal_name_during_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle legal name collection during course registration"""
    
    # Check if we're collecting legal name
    if not context.user_data.get('collecting_legal_name_for_registration'):
        return  # Let other handlers process this message
    
    user = update.effective_user
    text = update.message.text.strip()
    
    # Validate English only
    if not text.replace(' ', '').isalpha() or not text.isascii():
        await update.message.reply_text(
            "❌ يجب أن يكون الاسم باللغة الإنجليزية فقط\n"
            "❌ Name must be in English only\n\n"
            "الرجاء إدخال الاسم مرة أخرى.\nPlease enter the name again.",
            parse_mode='Markdown'
        )
        return  # Stay in current step
    
    # Determine which step we're on
    if 'legal_name_first' not in context.user_data:
        # Step 1: First name
        context.user_data['legal_name_first'] = text
        await update.message.reply_text(
            f"✅ تم حفظ: {text}\n\n"
            "🔹 *الخطوة 2/4:* أدخل اسم والدك\n"
            "🔹 *Step 2/4:* Enter your father's name",
            parse_mode='Markdown'
        )
        return
    
    elif 'legal_name_father' not in context.user_data:
        # Step 2: Father's name
        context.user_data['legal_name_father'] = text
        await update.message.reply_text(
            f"✅ تم حفظ: {text}\n\n"
            "🔹 *الخطوة 3/4:* أدخل اسم جدك\n"
            "🔹 *Step 3/4:* Enter your grandfather's name",
            parse_mode='Markdown'
        )
        return
    
    elif 'legal_name_grandfather' not in context.user_data:
        # Step 3: Grandfather's name
        context.user_data['legal_name_grandfather'] = text
        await update.message.reply_text(
            f"✅ تم حفظ: {text}\n\n"
            "🔹 *الخطوة 4/4:* أدخل اسم جد والدك\n"
            "🔹 *Step 4/4:* Enter your great-grandfather's name",
            parse_mode='Markdown'
        )
        return
    
    else:
        # Step 4: Great-grandfather's name - Save and proceed
        with get_db() as session:
            internal_user_id = context.user_data.get('registration_internal_user_id')
            
            if not internal_user_id:
                await update.message.reply_text(
                    "❌ حدث خطأ. يرجى المحاولة مرة أخرى.\n"
                    "❌ An error occurred. Please try again.",
                    reply_markup=back_to_main_keyboard()
                )
                context.user_data.clear()
                return
            
            # Save legal name
            success = crud.update_user_legal_name(
                session,
                internal_user_id,
                context.user_data['legal_name_first'],
                context.user_data['legal_name_father'],
                context.user_data['legal_name_grandfather'],
                text
            )
            
            if success:
                full_name = (
                    f"{context.user_data['legal_name_first']} "
                    f"{context.user_data['legal_name_father']} "
                    f"{context.user_data['legal_name_grandfather']} "
                    f"{text}"
                )
                
                await update.message.reply_text(
                    "✅ *تم حفظ اسمك القانوني بنجاح!*\n"
                    "✅ *Legal name saved successfully!*\n\n"
                    f"📋 *الاسم الكامل | Full Name:*\n{full_name}\n\n"
                    "جاري المتابعة إلى الدفع...\n"
                    "Proceeding to payment...",
                    parse_mode='Markdown'
                )
                
                logger.info(f"Legal name saved for user {internal_user_id}: {full_name}")
                
                # Clear legal name collection flags
                context.user_data.pop('collecting_legal_name_for_registration', None)
                context.user_data.pop('registration_internal_user_id', None)
                context.user_data.pop('legal_name_first', None)
                context.user_data.pop('legal_name_father', None)
                context.user_data.pop('legal_name_grandfather', None)
                
                # Now proceed with cart confirmation
                cart_items = crud.get_user_cart(session, internal_user_id)
                
                if not cart_items:
                    await update.message.reply_text(
                        "❌ عربة التسوق فارغة\n❌ Cart is empty",
                        reply_markup=back_to_main_keyboard()
                    )
                    return
                
                cart_totals = crud.calculate_cart_total(session, internal_user_id)
                total = cart_totals['total']

                
                # Create pending enrollments
                cart_items = crud.get_user_cart(session, internal_user_id)

                if not cart_items:
                    await update.message.reply_text(
                        "❌ عربة التسوق فارغة\n❌ Cart is empty",
                        reply_markup=back_to_main_keyboard()
                    )
                    return

                # Create pending enrollments with certificate info
                enrollment_ids = []
                for item in cart_items:
                    course = item.course
                    
                    # Calculate payment amount including certificate
                    payment_amount = course.price
                    if item.with_certificate and course.certificate_available:
                        payment_amount += course.certificate_price
                    
                    enrollment = crud.create_enrollment(session, internal_user_id, course.course_id, payment_amount)
                    enrollment.with_certificate = item.with_certificate
                    enrollment_ids.append(enrollment.enrollment_id)
                    logger.info(f"Created enrollment {enrollment.enrollment_id} for user {internal_user_id}, amount: {payment_amount}")

                session.commit()

                # Clear cart after creating enrollments
                crud.clear_user_cart(session, internal_user_id)
                session.commit()
                
                # Store in context for payment
                context.user_data['cart_total_for_payment'] = total
                context.user_data['pending_enrollment_ids_for_payment'] = enrollment_ids
                context.user_data['awaiting_receipt_upload'] = True
                context.user_data['expected_amount_for_gemini'] = total
                # Send payment instructions
                from utils.messages import payment_instructions_message
                from utils.keyboards import payment_upload_keyboard
                
                await update.message.reply_text(
                    payment_instructions_message(total),
                    reply_markup=payment_upload_keyboard(),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "❌ حدث خطأ أثناء حفظ الاسم. يرجى المحاولة مرة أخرى.\n"
                    "❌ Error saving name. Please try again.",
                    reply_markup=back_to_main_keyboard()
                )
                context.user_data.clear()

# Add after your existing course selection handler

async def course_add_to_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adding course to cart - ask about certificate first"""
    query = update.callback_query
    await query.answer()
    
    telegram_user_id = query.from_user.id
    course_id = int(query.data.split('_')[-1])
    
    with get_db() as session:
        user = crud.get_or_create_user(session, telegram_user_id)
        course = session.query(Course).filter(Course.course_id == course_id).first()
        
        if not course:
            await query.edit_message_text("❌ الدورة غير موجودة")
            return
        
        # Check if certificate is available for this course
        if course.certificate_available and course.certificate_price > 0:
            # Ask user if they want certificate
            message = f"""
📚 <b>{course.course_name}</b>

💰 سعر الدورة: {course.price} SDG
📜 سعر الشهادة: {course.certificate_price} SDG

هل تريد التسجيل مع شهادة؟
Do you want to register with a certificate?
"""
            await query.edit_message_text(
                message,
                reply_markup=certificate_option_keyboard(course_id),
                parse_mode='HTML'
            )
        else:
            # No certificate available, add directly to cart
            crud.add_to_cart_with_certificate(session, user.user_id, course_id, with_certificate=False)
            
            await query.edit_message_text(
                f"✅ تمت إضافة {course.course_name} إلى السلة\n\nAdded to cart!",
                reply_markup=course_selection_keyboard()
            )


async def register_certificate_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle certificate yes/no choice when registering directly from course details"""
    query = update.callback_query
    await query.answer()
    
    telegram_user_id = query.from_user.id
    callback_data = query.data  # register_cert_yes_123 or register_cert_no_123
    
    with_certificate = callback_data.startswith('register_cert_yes')
    course_id = int(callback_data.split('_')[-1])
    
    logger.info(f"User {telegram_user_id} chose certificate option for course {course_id} (direct registration flow): {with_certificate}")
    
    with get_db() as session:
        user = crud.get_or_create_user(session, telegram_user_id)
        internal_user_id = user.user_id
        
        course = session.query(Course).filter(Course.course_id == course_id).first()
        
        if not course:
            await query.edit_message_text("❌ الدورة غير موجودة")
            return
        
        # Create pending enrollment directly
        payment_amount = course.price
        if with_certificate:
            payment_amount += course.certificate_price
        
        enrollment = crud.create_enrollment(session, internal_user_id, course_id, payment_amount)
        enrollment.with_certificate = with_certificate
        session.commit()
        
        logger.info(f"Created pending enrollment {enrollment.enrollment_id} for user {telegram_user_id}, amount: {payment_amount}, with_cert: {with_certificate}")
        
        # Set context for payment flow
        context.user_data['cart_total_for_payment'] = payment_amount
        context.user_data['pending_enrollment_ids_for_payment'] = [enrollment.enrollment_id]
        context.user_data['awaiting_receipt_upload'] = True
        context.user_data['expected_amount_for_gemini'] = payment_amount
        
        # Proceed to payment
        from handlers.payment_handlers import proceed_to_payment_callback
        await proceed_to_payment_callback(update, context)


async def certificate_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle certificate yes/no choice"""
    query = update.callback_query
    await query.answer()
    
    telegram_user_id = query.from_user.id
    callback_data = query.data  # cert_yes_123 or cert_no_123
    
    with_certificate = callback_data.startswith('cert_yes')
    course_id = int(callback_data.split('_')[-1])
    
    with get_db() as session:
        user = crud.get_or_create_user(session, telegram_user_id)
        internal_user_id = user.user_id
        
        course = session.query(Course).filter(Course.course_id == course_id).first()
        
        if not course:
            await query.edit_message_text("❌ الدورة غير موجودة")
            return
        
        # Add to cart with certificate preference
        crud.add_to_cart_with_certificate(session, internal_user_id, course_id, with_certificate)
        session.commit()
        
        # Calculate price
        total_price = course.price
        if with_certificate:
            total_price += course.certificate_price
        
        cert_status = "✅ مع شهادة" if with_certificate else "❌ بدون شهادة"
        
        # Get updated cart and courses for keyboard
        available_courses = crud.get_available_courses_for_registration(session)
        cart_items = crud.get_user_cart(session, internal_user_id)
        selected_course_ids = [item.course_id for item in cart_items]
        
        # Calculate cart total with certificates
        cart_total_data = crud.calculate_cart_total(session, internal_user_id)
        cart_total = cart_total_data['total']
        
        message = f"""
✅ تمت الإضافة إلى السلة!
Added to cart!

📚 {course.course_name}
💰 السعر الإجمالي: {total_price:.0f} SDG
{cert_status}

🛒 إجمالي السلة: {cart_total:.0f} SDG
"""
        
        await query.edit_message_text(
            message,
            reply_markup=course_selection_keyboard(available_courses, selected_course_ids, cart_total)
        )

