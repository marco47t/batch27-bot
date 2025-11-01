"""
Menu handlers for Course Registration Bot
"""
from handlers import student_reviews, student_preferences
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest
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
        all_enrollments = session.query(crud.Enrollment).options(
            joinedload(crud.Enrollment.course)
        ).filter(
            crud.Enrollment.user_id == internal_user_id
        ).all()
        
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
        
        markup = my_courses_selection_keyboard(pending_enrollments, selected_ids)
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
        all_enrollments = session.query(crud.Enrollment).options(
            joinedload(crud.Enrollment.course)
        ).filter(
            crud.Enrollment.user_id == internal_user_id
        ).all()
        
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
        
        markup = my_courses_selection_keyboard(pending_enrollments, selected_ids)
        
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
        
        await query.edit_message_text(
            payment_instructions_message(total_amount),
            reply_markup=payment_upload_keyboard(),
            parse_mode='Markdown'
        )



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
    
    await query.edit_message_text(
        about_bot_message(),
        reply_markup=back_to_main_keyboard(),
        parse_mode='Markdown'
    )


async def back_to_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Back to Main Menu' button"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    log_user_action(user.id, "back_to_main", "")
    
    await query.edit_message_text(
        welcome_message(),
        reply_markup=courses_menu_keyboard()
    )

async def courses_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show courses menu (from inline callback)"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    log_user_action(user.id, "courses_menu_callback", "")
    
    await query.edit_message_text(
        courses_menu_message(),
        reply_markup=courses_menu_keyboard(),
        parse_mode='Markdown'
    )

async def my_course_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show enrolled course details"""
    query = update.callback_query
    await query.answer()
    
    enrollment_id = int(query.data.split('_')[-1])
    
    with get_db() as session:
        enrollment = crud.get_enrollment_by_id(session, enrollment_id)
        
        if not enrollment:
            await query.edit_message_text("❌ Course not found")
            return
        
        course = enrollment.course
        
        message = f"📚 **{course.course_name}**\n\n"
        
        # ✅ SHOW PARTIAL PAYMENT INFO
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
            message += f"✅ **مفعّل / Activated**\n\n"
            if course.telegram_group_link:
                keyboard = [
                    [InlineKeyboardButton("📱 انضم للمجموعة / Join Group", url=course.telegram_group_link)],
                    [InlineKeyboardButton("« العودة / Back", callback_data="my_courses_menu")]
                ]
            else:
                keyboard = [[InlineKeyboardButton("« العودة / Back", callback_data="my_courses_menu")]]
        else:
            message += f"⏳ **قيد المراجعة / Under Review**\n\n"
            keyboard = [[InlineKeyboardButton("« العودة / Back", callback_data="my_courses_menu")]]
        
        message += f"📅 التسجيل / Enrolled: {enrollment.enrollment_date.strftime('%Y-%m-%d')}"
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


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
        
        await query.edit_message_text(
            f"💳 **إكمال الدفع / Complete Payment**\n\n"
            f"⚠️ **المبلغ المتبقي:** {remaining:.0f} SDG\n"
            f"⚠️ **Remaining Amount:** {remaining:.0f} SDG\n\n"
            f"📤 أرسل إيصال الدفع الآن\n"
            f"📤 Send payment receipt now\n\n"
            f"🏦 رقم الحساب: `{config.EXPECTED_ACCOUNT_NUMBER}`",
            reply_markup=payment_upload_keyboard(),
            parse_mode='Markdown'
        )

async def contact_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle contact admin button from main menu"""
    query = update.callback_query
    await query.answer()
    
    message = """
📞 **التواصل مع الإدارة / Contact Admin**

يمكنك إرسال رسالتك الآن وسيتم إيصالها للإدارة.

Please send your message now and it will be forwarded to administration.

💡 يمكنك إرسال:
- نص
- صور
- مستندات

💡 You can send:
- Text
- Images
- Documents
"""
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=back_to_main_keyboard()
    )
    
    # Set state
    context.user_data['awaiting_support_message'] = True

async def contact_admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle "📞 التواصل مع الإدارة" button press"""
    user = update.effective_user
    
    message = """
📞 **التواصل مع الإدارة / Contact Admin**

يمكنك إرسال رسالتك الآن وسيتم إيصالها للإدارة.

Please send your message now and it will be forwarded to administration.

💡 يمكنك إرسال:
- نص / Text
- صور / Images  
- مستندات / Documents

⬇️ أرسل رسالتك الآن
⬇️ Send your message now
"""
    
    await update.message.reply_text(
        message,
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_support_message'] = True
    logger.info(f"User {user.id} clicked contact admin button")

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
