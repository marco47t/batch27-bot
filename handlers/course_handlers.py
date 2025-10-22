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
        courses = [item.course for item in cart_items]
        total = sum(course.price for course in courses)
        
        # Add remaining balances from pending enrollments
        for enrollment in pending_enrollments:
            paid = enrollment.amount_paid or 0
            remaining = enrollment.payment_amount - paid
            if remaining > 0:
                total += remaining
        
        # ✅ PASS PENDING ENROLLMENTS TO MESSAGE FUNCTION
        from utils.messages import cart_message
        message = cart_message(courses, total, pending_enrollments)
        
        logger.info(f"User {telegram_user_id} cart: {len(cart_items)} new items + {len(pending_enrollments)} pending, total={total:.0f}")
        
        await query.edit_message_text(
            message,
            reply_markup=cart_keyboard(),
            parse_mode='Markdown'
        )



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
                
                courses = [item.course for item in cart_items]
                total = sum(course.price for course in courses)
                
                # Create pending enrollments
                enrollment_ids = []
                for course in courses:
                    enrollment = crud.create_enrollment(session, internal_user_id, course.course_id, course.price)
                    enrollment_ids.append(enrollment.enrollment_id)
                    logger.info(f"Created enrollment {enrollment.enrollment_id} for user {internal_user_id}")
                
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
