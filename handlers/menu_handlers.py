"""
Menu handlers for Course Registration Bot
"""
from handlers import student_reviews, student_preferences
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from datetime import datetime, timedelta
import config
from utils.keyboards import (
    main_menu_reply_keyboard,
    courses_menu_keyboard,
    back_to_main_keyboard,
    my_courses_selection_keyboard,
    payment_upload_keyboard
)
from utils.messages import (
    payment_instructions_message,
    welcome_message,
    courses_menu_message,
    error_message,
    my_courses_message,
    about_bot_message
)
from utils.helpers import (
    get_user_info,
    get_chat_id,
    log_user_action
)
from database import crud, get_db
from sqlalchemy.orm import joinedload
from database.models import PaymentStatus
import logging

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command and show main menu with ReplyKeyboard"""
    user = get_user_info(update)
    chat_id = get_chat_id(update)
    
    log_user_action(user.id, "start_command", f"chat_id={chat_id}")
    
    with get_db() as session:
        crud.get_or_create_user(
            session,
            telegram_user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        session.commit()
    
    await update.message.reply_text(
        welcome_message(),
        reply_markup=main_menu_reply_keyboard()
    )


async def handle_courses_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'الدورات المتاحة' from ReplyKeyboard"""
    user = get_user_info(update)
    log_user_action(user.id, "courses_menu_from_message", "")
    
    await update.message.reply_text(
        courses_menu_message(),
        reply_markup=courses_menu_keyboard(),
        parse_mode='Markdown'
    )

async def rate_course_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '3- تقييم دورة ⭐' button"""
    # Redirect to the rate course command
    await student_reviews.rate_course_command(update, context)

async def preferences_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '4- الإشعارات 🔔' button"""
    # Redirect to the preferences command
    await student_preferences.preferences_command(update, context)
async def handle_my_courses_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show my_courses view from a text message (ReplyKeyboard)"""
    telegram_user_id = update.effective_user.id
    context.user_data.setdefault('selected_pending_enrollments', [])
    
    with get_db() as session:
        # GET INTERNAL USER ID
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=telegram_user_id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name
        )
        session.flush()
        internal_user_id = db_user.user_id
        
        # Query with internal_user_id
        all_enrollments_query = session.query(crud.Enrollment).options(
            joinedload(crud.Enrollment.course)
        ).filter(
            crud.Enrollment.user_id == internal_user_id
        )
        
        # Apply the new filtering logic
        now = datetime.now()
        seven_days_ago = now - timedelta(days=7)
        
        filtered_enrollments = []
        for enrollment in all_enrollments_query.all():
            course = enrollment.course
            if not course or not course.end_date:
                filtered_enrollments.append(enrollment)
                continue

            # Rule 1: Hide if it has a certificate and the end date has passed
            if enrollment.with_certificate and course.end_date < now:
                continue
            
            # Rule 2: Hide if it has NO certificate and the end date was more than 7 days ago
            if not enrollment.with_certificate and course.end_date < seven_days_ago:
                continue
            
            filtered_enrollments.append(enrollment)

        all_enrollments = filtered_enrollments
        
        pending_enrollments = [e for e in all_enrollments if e.payment_status.value in ['PENDING', 'FAILED']]
        selected_ids = context.user_data['selected_pending_enrollments']
        
        # ✅ CALCULATE REMAINING BALANCE INSTEAD OF FULL AMOUNT
        total_selected_amount = 0
        for e in pending_enrollments:
            if e.enrollment_id in selected_ids and e.payment_amount:
                paid = e.amount_paid or 0
                remaining = e.payment_amount - paid
                total_selected_amount += remaining
        
        log_user_action(telegram_user_id, "my_courses_view_from_message")
        
        new_text = my_courses_message(
            all_enrollments,
            pending_count=len(pending_enrollments),
            selected_count=len(selected_ids),
            total_selected=total_selected_amount
        )
        
        markup = my_courses_selection_keyboard(all_enrollments, selected_ids)
        await update.message.reply_text(new_text, reply_markup=markup, parse_mode='Markdown')


async def handle_about_bot_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'حول البوت' from ReplyKeyboard"""
    user = get_user_info(update)
    log_user_action(user.id, "about_bot_from_message", "")
    
    await update.message.reply_text(
        about_bot_message(),
        reply_markup=main_menu_reply_keyboard(),
        parse_mode='Markdown'
    )


async def my_courses_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the user's enrolled courses and payment selection (from INLINE callback)"""
    query = update.callback_query
    telegram_user_id = query.from_user.id
    context.user_data.setdefault('selected_pending_enrollments', [])
    
    with get_db() as session:
        # GET INTERNAL USER ID
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=telegram_user_id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )
        session.flush()
        internal_user_id = db_user.user_id
        
        # Query with internal_user_id
        all_enrollments_query = session.query(crud.Enrollment).options(
            joinedload(crud.Enrollment.course)
        ).filter(
            crud.Enrollment.user_id == internal_user_id
        )
        
        # Apply the new filtering logic
        now = datetime.now()
        seven_days_ago = now - timedelta(days=7)
        
        filtered_enrollments = []
        for enrollment in all_enrollments_query.all():
            course = enrollment.course
            if not course or not course.end_date:
                filtered_enrollments.append(enrollment)
                continue

            # Rule 1: Hide if it has a certificate and the end date has passed
            if enrollment.with_certificate and course.end_date < now:
                continue
            
            # Rule 2: Hide if it has NO certificate and the end date was more than 7 days ago
            if not enrollment.with_certificate and course.end_date < seven_days_ago:
                continue
            
            filtered_enrollments.append(enrollment)

        all_enrollments = filtered_enrollments
        
        pending_enrollments = [e for e in all_enrollments if e.payment_status.value in ['PENDING', 'FAILED']]
        selected_ids = context.user_data['selected_pending_enrollments']
        
        # ✅ CALCULATE REMAINING BALANCE INSTEAD OF FULL AMOUNT
        total_selected_amount = 0
        for e in pending_enrollments:
            if e.enrollment_id in selected_ids and e.payment_amount:
                paid = e.amount_paid or 0
                remaining = e.payment_amount - paid
                total_selected_amount += remaining
        
        log_user_action(telegram_user_id, "my_courses_view_from_callback")
        
        new_text = my_courses_message(
            all_enrollments,
            pending_count=len(pending_enrollments),
            selected_count=len(selected_ids),
            total_selected=total_selected_amount
        )
        
        markup = my_courses_selection_keyboard(all_enrollments, selected_ids)
        
        try:
            await query.edit_message_text(new_text, reply_markup=markup, parse_mode='Markdown')
        except BadRequest as e:
            if "Message is not modified" in str(e):
                logger.warning("Message not modified, skipping edit.")
                pass
            else:
                raise


async def my_course_select_deselect_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle selection of a pending enrollment for payment"""
    query = update.callback_query
    await query.answer()
    
    telegram_user_id = query.from_user.id
    
    # === FIX START ===
    # Correctly parse the callback data
    # e.g., 'my_course_select_123' -> ['my', 'course', 'select', '123']
    parts = query.data.split('_')
    if len(parts) < 4:
        logger.error(f"Invalid callback data format: {query.data}")
        return

    action = parts[2]  # This is now 'select' or 'deselect'
    enrollment_id = int(parts[3]) # This is now the ID
    # === FIX END ===
    
    # Get internal user ID and verify enrollment ownership
    with get_db() as session:
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=telegram_user_id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )
        session.flush()
        internal_user_id = db_user.user_id
        
        # Verify this enrollment belongs to this user
        enrollment = crud.get_enrollment_by_id(session, enrollment_id)
        if not enrollment or enrollment.user_id != internal_user_id:
            await query.answer("❌ خطأ: لا يمكنك اختيار هذه الدورة", show_alert=True)
            return
    
    # Initialize list if not exists
    context.user_data.setdefault('selected_pending_enrollments', [])
    
    # Toggle selection
    if action == 'select':
        if enrollment_id not in context.user_data['selected_pending_enrollments']:
            context.user_data['selected_pending_enrollments'].append(enrollment_id)
            log_user_action(telegram_user_id, "enrollment_selected", f"enrollment_id={enrollment_id}")
    elif action == 'deselect':
        if enrollment_id in context.user_data['selected_pending_enrollments']:
            context.user_data['selected_pending_enrollments'].remove(enrollment_id)
            log_user_action(telegram_user_id, "enrollment_deselected", f"enrollment_id={enrollment_id}")
    
    # Refresh the view by calling my_courses_callback
    await my_courses_callback(update, context)


async def proceed_to_pay_selected_pending_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Proceed to payment for selected pending courses"""
    query = update.callback_query
    await query.answer()
    
    telegram_user_id = query.from_user.id
    selected_ids = context.user_data.get('selected_pending_enrollments', [])
    
    if not selected_ids:
        await query.answer("[translate:لم تختر أي دورات للدفع]!", show_alert=True)
        return
    
    with get_db() as session:
        # GET INTERNAL USER ID
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=telegram_user_id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )
        session.flush()
        internal_user_id = db_user.user_id
        
        # Query with internal_user_id
        enrollments_to_pay = session.query(crud.Enrollment).filter(
            crud.Enrollment.enrollment_id.in_(selected_ids),
            crud.Enrollment.user_id == internal_user_id
        ).all()
        
        # ✅ CALCULATE TOTAL REMAINING BALANCE
        total_amount = 0
        for e in enrollments_to_pay:
            if e.payment_amount:
                paid = e.amount_paid or 0
                remaining = e.payment_amount - paid
                total_amount += remaining
        
        if total_amount <= 0:
            await query.answer("[translate:حدث خطأ في حساب المبلغ]", show_alert=True)
            return
        
        context.user_data["awaiting_receipt_upload"] = True
        context.user_data["current_payment_enrollment_ids"] = selected_ids
        context.user_data["current_payment_total"] = total_amount
        context.user_data.pop("resubmission_enrollment_id", None)
        context.user_data['selected_pending_enrollments'] = []
        
        try:
            await query.edit_message_text(
                payment_instructions_message(total_amount),
                reply_markup=payment_upload_keyboard(),
                parse_mode='Markdown'
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                logger.warning("Message not modified, skipping edit in proceed_to_pay_selected_pending_callback.")
                pass
            else:
                raise



async def cancel_selected_pending_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel (delete) selected PENDING or FAILED enrollments."""
    query = update.callback_query
    await query.answer()
    telegram_user_id = query.from_user.id
    selected_ids = context.user_data.get('selected_pending_enrollments', [])

    if not selected_ids:
        await query.answer("لم تختر أي دورات للإلغاء!", show_alert=True)
        return

    with get_db() as session:
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=telegram_user_id,
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )
        session.flush()
        internal_user_id = db_user.user_id

        # Find and delete the enrollments
        enrollments_to_delete = session.query(crud.Enrollment).filter(
            crud.Enrollment.enrollment_id.in_(selected_ids),
            crud.Enrollment.user_id == internal_user_id
        ).all()

        deleted_count = len(enrollments_to_delete)
        for enrollment in enrollments_to_delete:
            session.delete(enrollment)
        
        session.commit()
        
        log_user_action(telegram_user_id, "enrollments_cancelled", f"count={deleted_count}, ids={selected_ids}")

    # Clear selection from user_data
    context.user_data['selected_pending_enrollments'] = []
    
    await query.answer(f"✅ تم إلغاء {deleted_count} تسجيل بنجاح", show_alert=True)

    # Refresh the view
    await my_courses_callback(update, context)


async def about_bot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'About Bot' button"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    log_user_action(user.id, "about_bot_callback", "")
    
    try:
        await query.edit_message_text(
            about_bot_message(),
            reply_markup=back_to_main_keyboard(),
            parse_mode='Markdown'
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.warning("Message not modified, skipping edit in about_bot_callback.")
            pass
        else:
            raise


async def back_to_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Back to Main Menu' button"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    log_user_action(user.id, "back_to_main", "")
    
    try:
        await query.edit_message_text(
            welcome_message(),
            reply_markup=courses_menu_keyboard()
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.warning("Message not modified, skipping edit in back_to_main_callback.")
            pass
        else:
            raise

async def courses_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show courses menu (from inline callback)"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    log_user_action(user.id, "courses_menu_callback", "")
    
    try:
        await query.edit_message_text(
            courses_menu_message(),
            reply_markup=courses_menu_keyboard(),
            parse_mode='Markdown'
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.warning("Message not modified, skipping edit in courses_menu_callback.")
            pass
        else:
            raise

async def my_course_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show enrolled course details and certificate upgrade option."""
    query = update.callback_query
    await query.answer()
    
    enrollment_id = int(query.data.split('_')[-1])
    
    with get_db() as session:
        enrollment = crud.get_enrollment_by_id(session, enrollment_id)
        
        if not enrollment:
            try:
                await query.edit_message_text("❌ Course not found")
            except BadRequest: pass
            return
        
        course = enrollment.course
        
        message = f"📚 **{course.course_name}**\n\n"
        keyboard = []

        if enrollment.payment_status == PaymentStatus.PENDING and enrollment.amount_paid > 0:
            remaining = enrollment.payment_amount - enrollment.amount_paid
            message += (
                f"⚠️ **الدفع غير مكتمل / Payment Incomplete**\n\n"
                f"💰 المدفوع / Paid: {enrollment.amount_paid:.0f} SDG\n"
                f"📊 المطلوب / Required: {enrollment.payment_amount:.0f} SDG\n"
                f"⚠️ المتبقي / Remaining: **{remaining:.0f} SDG**\n\n"
            )
            keyboard = [
                [InlineKeyboardButton("💳 إكمال الدفع / Complete Payment", callback_data=f"complete_payment_{enrollment_id}")],
                [InlineKeyboardButton("« العودة / Back", callback_data="my_courses_menu")]
            ]
        elif enrollment.payment_status == PaymentStatus.VERIFIED:
            message += f"✅ **مفعّل**\n\n"
            
            # Add links directly to the message
            if course.telegram_group_link:
                message += f"📱 **رابط مجموعة التليجرام:**\n{course.telegram_group_link}\n\n"
            if enrollment.with_certificate and course.whatsapp_group_link:
                message += f"💬 **رابط مجموعة الواتساب (للشهادة):**\n{course.whatsapp_group_link}\n\n"

            # Check if user can register for a certificate
            can_register_for_cert = False
            if (not enrollment.with_certificate and 
                course.certificate_available and 
                course.certificate_price > 0 and
                course.end_date):
                
                deadline = course.end_date + timedelta(days=7)
                now = datetime.now()
                
                if (course.start_date or datetime.min) <= now <= deadline:
                    can_register_for_cert = True

            if can_register_for_cert:
                keyboard.append([InlineKeyboardButton(f"📜 تسجيل للشهادة ({course.certificate_price:.0f} SDG)", callback_data=f"cert_upgrade_{enrollment_id}")])
            
            keyboard.append([InlineKeyboardButton("« العودة", callback_data="my_courses_menu")])

        else: # FAILED or PENDING with 0 paid
            message += f"⏳ **قيد المراجعة**\n\n"
            keyboard = [[InlineKeyboardButton("« العودة", callback_data="my_courses_menu")]]
        
        message += f"📅 تاريخ التسجيل: {enrollment.enrollment_date.strftime('%Y-%m-%d')}"
        
        try:
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                logger.warning("Message not modified, skipping edit in my_course_detail_callback.")
                pass
            else:
                raise

async def complete_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle complete payment button"""
    query = update.callback_query
    await query.answer()
    
    enrollment_id = int(query.data.split('_')[-1])
    
    with get_db() as session:
        enrollment = crud.get_enrollment_by_id(session, enrollment_id)
        
        if not enrollment:
            await query.edit_message_text("❌ Error")
            return
        
        remaining = enrollment.payment_amount - enrollment.amount_paid
        
        # Set context for payment upload
        context.user_data["resubmission_enrollment_id"] = enrollment_id
        context.user_data["reupload_amount"] = remaining
        context.user_data["awaiting_receipt_upload"] = True
        
        try:
            await query.edit_message_text(
                f"💳 **إكمال الدفع**\n\n"
                f"⚠️ **المبلغ المتبقي:** {remaining:.0f} SDG\n\n"
                f"📤 أرسل إيصال الدفع الآن\n\n"
                f"🏦 رقم الحساب: `{config.EXPECTED_ACCOUNT_NUMBER}`",
                reply_markup=payment_upload_keyboard(),
                parse_mode='Markdown'
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                logger.warning("Message not modified, skipping edit in complete_payment_callback.")
                pass
            else:
                raise

async def contact_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle contact admin button from main menu"""
    query = update.callback_query
    await query.answer()
    
    message = """
📞 **التواصل مع الإدارة**

الرجاء إرسال رسالتك الآن.
يمكنك إرسال نص، صور، أو مستندات.
"""
    
    try:
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=back_to_main_keyboard()
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.warning("Message not modified, skipping edit in contact_admin_callback.")
            pass
        else:
            raise
    
    # Set state
    context.user_data['awaiting_support_message'] = True

async def contact_admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles 'Contact Admin' text button from main menu."""
    
    message = """
📞 **التواصل مع الإدارة**

الرجاء إرسال رسالتك الآن.
يمكنك إرسال نص، صور، أو مستندات.
"""
    
    await update.message.reply_text(
        message,
        parse_mode='Markdown',
        reply_markup=back_to_main_keyboard()
    )
    
    # Set flag in user data
    context.user_data['awaiting_support_message'] = True
    logger.info(f"User {update.effective_user.id} initiated contact with admin via text button")

async def follow_us_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'تابعونا' button from main menu"""
    user = get_user_info(update)
    log_user_action(user.id, "follow_us_button", "")
    
    from utils.messages import follow_us_message
    
    await update.message.reply_text(
        follow_us_message(),
        parse_mode='Markdown',
        reply_markup=main_menu_reply_keyboard()
    )

async def certificate_upgrade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the process for a verified user to pay for a certificate."""
    query = update.callback_query
    await query.answer()

    enrollment_id = int(query.data.split('_')[-1])

    with get_db() as session:
        enrollment = crud.get_enrollment_by_id(session, enrollment_id)

        if not enrollment or not enrollment.course:
            try:
                await query.edit_message_text("❌ An error occurred. Enrollment not found.")
            except BadRequest: pass
            return

        course = enrollment.course
        certificate_price = course.certificate_price

        # Set user_data for the payment flow
        context.user_data['awaiting_receipt_upload'] = True
        context.user_data['certificate_upgrade_enrollment_id'] = enrollment_id
        context.user_data['expected_amount_for_gemini'] = certificate_price
        # Clear other payment-related keys to avoid conflicts
        context.user_data.pop('resubmission_enrollment_id', None)
        context.user_data.pop('current_payment_enrollment_ids', None)


        # Define account numbers with their bank names
        bank_accounts = [
            (config.BANKAK_ACCOUNT, "بنكك"),
            (config.CASHI_ACCOUNT, "كاشي"),
            (config.FAWRY_ACCOUNT, "فوري")
        ]
        
        # Filter out None values
        valid_accounts = [(acc, name) for acc, name in bank_accounts if acc]
        
        # Build accounts display text
        if len(valid_accounts) == 1:
            accounts_text = f"🏦 {valid_accounts[0][1]}: `{valid_accounts[0][0]}`"
        else:
            accounts_text = "🏦 أرقام الحسابات المقبولة:\n" + "\n".join(
                [f"• {name}: `{acc}`" for acc, name in valid_accounts]
            )

        message = (
            f"📜 **تسجيل للحصول على شهادة**\n\n"
            f"📚 الدورة: {course.course_name}\n"
            f"💰 سعر الشهادة: **{certificate_price:.0f} SDG**\n\n"
            f"لإتمام التسجيل، يرجى إرسال إيصال دفع بالمبلغ المطلوب.\n\n"
            f"{accounts_text}\n\n"
            f"👤 الاسم: {config.EXPECTED_ACCOUNT_NAME}"
        )

        try:
            await query.edit_message_text(
                text=message,
                reply_markup=payment_upload_keyboard(),
                parse_mode='Markdown'
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                logger.warning("Message not modified in certificate_upgrade_callback.")
                pass
            else:
                raise
