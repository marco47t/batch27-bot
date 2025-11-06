"""
Admin dashboard and commands
"""

from venv import logger
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from utils.keyboards import admin_menu_keyboard, admin_transaction_keyboard, back_to_main_keyboard
from utils.messages import admin_stats_message, admin_transaction_message, error_message
from utils.helpers import is_admin_user, send_admin_notification
from database import crud, get_db
from database.models import PaymentStatus, TransactionStatus
import config
from utils.messages import admin_help_message

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for /admin command/menu"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text(error_message("admin_only"), reply_markup=back_to_main_keyboard())
        return
    
    await update.message.reply_text(
        "🛠️ **Admin Dashboard**",
        reply_markup=admin_menu_keyboard(),
        parse_mode='Markdown'
    )

async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show registration statistics"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if not is_admin_user(user_id):
        await query.edit_message_text(error_message("admin_only"), reply_markup=back_to_main_keyboard())
        return
    
    with get_db() as session:
        stats = crud.get_enrollment_stats(session)
        
    try:
        await query.edit_message_text(
            admin_stats_message(stats),
            reply_markup=admin_menu_keyboard(),
            parse_mode='Markdown'
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.warning("Message not modified, skipping edit in admin_stats_callback.")
            pass
        else:
            raise

async def admin_pending_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all pending/rejected transactions for manual review"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_admin_user(user_id):
        await query.edit_message_text(error_message("admin_only"), reply_markup=back_to_main_keyboard())
        return
    
    with get_db() as session:
        transactions = crud.get_pending_transactions(session)
        
        if not transactions:
            # FIX: Check if message content is different before editing
            new_text = "🎉 No pending transactions."
            new_markup = admin_menu_keyboard()
            
            # Only edit if content is actually different
            try:
                if query.message.text != new_text:
                    await query.edit_message_text(new_text, reply_markup=new_markup)
                else:
                    # Message is identical, just answer the callback without editing
                    await query.answer("No pending transactions found.", show_alert=False)
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    logger.warning("Message not modified, skipping edit in admin_pending_callback (no pending transactions).")
                    pass
                else:
                    raise
            except Exception as e:
                # Fallback: just answer the callback
                logger.error(f"Error editing message in admin_pending_callback (no pending transactions): {e}")
                await query.answer("No pending transactions.", show_alert=False)
            return
        
        # Display first transaction to review (can add pagination)
        transaction = transactions[0]

        try:
            await query.edit_message_text(
                admin_transaction_message(transaction),
                reply_markup=admin_transaction_keyboard(transaction.transaction_id),
                parse_mode='Markdown'
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                logger.warning("Message not modified, skipping edit in admin_pending_callback (display transaction).")
                pass
            else:
                raise
        except Exception as e:
            if "message is not modified" in str(e).lower():
                await query.answer("Already viewing this transaction.", show_alert=False)
            else:
                raise



async def notify_user_payment_decision(context: ContextTypes.DEFAULT_TYPE, 
                                       user_chat_id: int, 
                                       decision: str, 
                                       course_names: list,
                                       group_links: list = None,
                                       reason: str = None):
    """
    Notify user about payment approval/rejection
    
    Args:
        context: Bot context
        user_chat_id: User's Telegram chat ID
        decision: "approved" or "rejected"
        course_names: List of course names
        group_links: List of group links (optional)
        reason: Rejection reason (required if decision is "rejected")
    """
    if decision == "approved":
        courses_text = "\n".join([f"✅ {name}" for name in course_names])
        
        # Add group links if available
        links_text = ""
        if group_links and any(group_links):
            links_text = "\n\n**روابط المجموعات:**\n"
            for idx, link in enumerate(group_links):
                if link:
                    links_text += f"{idx + 1}. {link}\n"
        
        message = f"""
🎉 **تم قبول دفعتك!**

تم التحقق من الدفعة الخاصة بك وتم تسجيلك بنجاح في الدورات التالية:

{courses_text}{links_text}

يمكنك الآن الوصول إلى مجموعات الدورات من قائمة "دوراتي" 📋.
"""
    else:  # rejected
        message = f"""
❌ **تم رفض دفعتك**

للأسف، لم يتم قبول الدفعة المرسلة.

**السبب:** {reason or 'لم يتم تحديد السبب'}

يرجى إعادة إرسال إيصال صحيح من قائمة "دوراتي" → "إعادة محاولة الدفع".

إذا كانت لديك أية استفسارات، يرجى التواصل مع الإدارة.
"""
    
    try:
        await context.bot.send_message(
            chat_id=user_chat_id,
            text=message,
            parse_mode='Markdown'
        )
        return True
    except Exception as e:
        print(f"Failed to notify user {user_chat_id}: {e}")
        return False

async def admin_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approves a transaction/payment. Edits the source message to confirm."""
    query = update.callback_query
    await query.answer("Processing approval...")
    admin_user = query.from_user

    if not is_admin_user(admin_user.id):
        await query.edit_message_text(error_message("admin_only"))
        return

    prefix = config.CallbackPrefix.ADMIN_APPROVE
    transaction_id = int(query.data[len(prefix):])

    user_chat_id, course_names, group_links = None, [], []

    with get_db() as session:
        transaction = crud.update_transaction(session, transaction_id, status="VERIFIED", admin_reviewed=admin_user.id)
        if not transaction:
            await query.edit_message_text("❌ Transaction not found.")
            return

        enrollment = transaction.enrollment
        crud.update_enrollment_status(session, enrollment.enrollment_id, "verified", receipt_path=transaction.receipt_image_path)
        
        user = enrollment.user
        user_chat_id = user.telegram_chat_id
        
        # Explicitly access course to ensure it's loaded before session closes
        course = enrollment.course
        if course:
            # Force load the course_name attribute
            course_name = str(course.course_name) if course.course_name else "Unknown Course"
            telegram_group_link = str(course.telegram_group_link) if course.telegram_group_link else None
            
            course_names.append(course_name)
            if telegram_group_link:
                group_links.append(telegram_group_link)
        
        session.commit()


    if user_chat_id and course_names:
        await notify_user_payment_decision(
            context,
            user_chat_id,
            decision="approved",
            course_names=course_names,
            group_links=group_links
        )
        from handlers.group_registration import send_course_invite_link
        await send_course_invite_link(update, context, user_chat_id, enrollment.course_id)
        
    final_text = f"✅ تم قبول المعاملة {transaction_id} بواسطة {admin_user.first_name}.\n\n✉️ تم إشعار المستخدم بنجاح."

    # Edit the original admin message (notification or panel) to show it's completed
    try:
        if query.message.caption:
            await query.edit_message_caption(caption=final_text, reply_markup=None)
        else:
            await query.edit_message_text(text=final_text, reply_markup=None)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.warning("Message not modified, skipping edit in admin_approve_callback.")
            pass
        else:
            raise
    except Exception as e:
        # Fallback if editing fails
        logger.error(f"Error editing message in admin_approve_callback: {e}")
        await query.message.reply_text(final_text)

async def admin_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin rejects a transaction/payment (add reason). Edits the source message."""
    query = update.callback_query
    await query.answer("Provide rejection reason...")
    admin_user = query.from_user
    
    if not is_admin_user(admin_user.id):
        await query.edit_message_text(error_message("admin_only"))
        return
    
    prefix = config.CallbackPrefix.ADMIN_REJECT
    transaction_id = int(query.data[len(prefix):])
    
    context.user_data["pending_rejection_transaction_id"] = transaction_id
    context.user_data["awaiting_rejection_reason"] = True
    
    prompt_text = f"❌ Transaction {transaction_id} rejected by {admin_user.first_name}.\n\nPlease send the rejection reason now."
    try:
        if query.message.caption:
            await query.edit_message_caption(caption=prompt_text, reply_markup=None)
        else:
            await query.edit_message_text(text=prompt_text, reply_markup=None)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.warning("Message not modified, skipping edit in admin_reject_callback.")
            pass
        else:
            raise
    except Exception as e:
        logger.error(f"Error editing message in admin_reject_callback: {e}")
        await query.message.reply_text(prompt_text)

async def rejection_reason_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin sending rejection reason after clicking reject"""
    user_id = update.effective_user.id
    
    # Add debug logging
    logger.info(f"rejection_reason_message_handler called by user {user_id}")
    logger.info(f"awaiting_rejection_reason: {context.user_data.get('awaiting_rejection_reason')}")
    logger.info(f"awaiting_failed_rejection_reason: {context.user_data.get('awaiting_failed_rejection_reason')}")
    logger.info(f"pending_rejection_transaction_id: {context.user_data.get('pending_rejection_transaction_id')}")
    
    if not is_admin_user(user_id):
        logger.warning(f"User {user_id} is not admin")
        return
    
    if context.user_data.get("awaiting_failed_rejection_reason"):
        logger.info("Delegating to failed_rejection_reason_handler")
        await failed_rejection_reason_handler(update, context)
        return
    
    # Check if we're expecting a rejection reason
    if not context.user_data.get("awaiting_rejection_reason"):
        logger.warning(f"Not awaiting rejection reason for user {user_id}")
        return
    
    transaction_id = context.user_data.get("pending_rejection_transaction_id")
    if not transaction_id:
        logger.error("No pending_rejection_transaction_id found")
        return
    
    reason = update.message.text
    logger.info(f"Processing rejection for transaction {transaction_id} with reason: {reason}")
    
    
    # Variables to store before session closes
    user_chat_id = None
    course_names = []
    
    with get_db() as session:
        # Update transaction status with rejection reason
        transaction = crud.update_transaction(
            session, 
            transaction_id, 
            status="rejected", 
            failure_reason=reason, 
            admin_reviewed=user_id
        )
        
        if not transaction:
            await update.message.reply_text(
                "❌ Transaction not found.",
                reply_markup=admin_menu_keyboard()
            )
            context.user_data.pop("pending_rejection_transaction_id", None)
            context.user_data.pop("awaiting_rejection_reason", None)
            return
        
        # Get enrollment and update status
        enrollment = transaction.enrollment
        crud.update_enrollment_status(
            session, 
            enrollment.enrollment_id, 
            "failed", 
            admin_notes=reason
        )
        
        # Get user info for notification - force load relationships
        user = enrollment.user
        user_chat_id = user.telegram_chat_id
        
        # Get course info - force load while session is active
        course = enrollment.course
        course_names.append(course.course_name)
        
        # Commit changes
        session.commit()
    
    # Now session is closed, notify user
    if user_chat_id:
        notification_sent = await notify_user_payment_decision(
            context,
            user_chat_id,
            decision="rejected",
            course_names=course_names,
            reason=reason
        )
        
        if notification_sent:
            await update.message.reply_text(
                f"❌ Transaction {transaction_id} rejected.\n\n**Reason:** {reason}\n\n✉️ User has been notified.",
                reply_markup=admin_menu_keyboard(),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ Transaction {transaction_id} rejected.\n\n**Reason:** {reason}\n\n⚠️ Failed to notify user.",
                reply_markup=admin_menu_keyboard(),
                parse_mode='Markdown'
            )
    else:
        await update.message.reply_text(
            f"❌ Transaction {transaction_id} rejected: {reason}",
            reply_markup=admin_menu_keyboard()
        )
    
    await send_admin_notification(
        context, 
        f"❌ Transaction {transaction_id} rejected by admin {user_id}: {reason}"
    )
    
    # Clear context data
    context.user_data.pop("pending_rejection_transaction_id", None)
    context.user_data.pop("awaiting_rejection_reason", None)

async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin help with all commands"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text(
            error_message("admin_only"),
            reply_markup=back_to_main_keyboard()
        )
        return
    
    await update.message.reply_text(
        admin_help_message(),
        parse_mode='Markdown',
        reply_markup=back_to_main_keyboard()
    )

async def admin_approve_failed_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approves a failed receipt immediately from notification"""
    query = update.callback_query
    await query.answer("Processing approval...")
    
    admin_user = query.from_user
    if not is_admin_user(admin_user.id):
        await query.edit_message_caption(caption=error_message("admin_only"))
        return
    
    # Parse callback data: "enrollment_ids|telegram_user_id"
    prefix = config.CallbackPrefix.ADMIN_APPROVE_FAILED
    data = query.data[len(prefix):]
    enrollment_ids_str, telegram_user_id_str = data.split("|")
    enrollment_ids = [int(eid.strip()) for eid in enrollment_ids_str.split(",")]
    telegram_user_id = int(telegram_user_id_str)
    
    user_chat_id, course_names, group_links = None, [], []
    
    with get_db() as session:
        for enrollment_id in enrollment_ids:
            enrollment = crud.get_enrollment_by_id(session, enrollment_id)
            if not enrollment:
                continue
            
            # Update enrollment to verified
            crud.update_enrollment_status(
                session, 
                enrollment_id, 
                PaymentStatus.VERIFIED,
                admin_notes=f"Manually approved by admin {admin_user.first_name}"
            )
            
            # Update transaction if exists
            from database.models import Transaction
            transaction = session.query(Transaction).filter(
                Transaction.enrollment_id == enrollment_id
            ).order_by(Transaction.submitted_date.desc()).first()
            
            if transaction:
                crud.update_transaction(
                    session,
                    transaction.transaction_id,
                    status=TransactionStatus.APPROVED,
                    admin_reviewed=admin_user.id
                )
            
            # Collect course info
            user = enrollment.user
            user_chat_id = user.telegram_chat_id
            
            # Force load course attributes before session closes
            course = enrollment.course
            if course:
                course_name = str(course.course_name) if course.course_name else "Unknown Course"
                telegram_group_link = str(course.telegram_group_link) if course.telegram_group_link else None
                
                course_names.append(course_name)
                if telegram_group_link:
                    group_links.append(telegram_group_link)

        
        # Clear user's cart if this was initial payment
        if enrollment_ids:
            first_enrollment = crud.get_enrollment_by_id(session, enrollment_ids[0])
            if first_enrollment:
                crud.clear_user_cart(session, first_enrollment.user_id)
        
        session.commit()
    
    # Notify user
    if user_chat_id:
        await notify_user_payment_decision(
            context,
            user_chat_id,
            decision="approved",
            course_names=course_names,
            group_links=group_links
        )
        from handlers.group_registration import send_course_invite_link
        with get_db() as session:
            for enrollment_id in enrollment_ids:
                enrollment = crud.get_enrollment_by_id(session, enrollment_id)
                if enrollment:
                    await send_course_invite_link(update, context, user_chat_id, enrollment.course_id)
    
    # Update admin message
    final_text = f"✅ Enrollments {enrollment_ids_str} approved by {admin_user.first_name}.\n\n✉️ User {telegram_user_id} has been notified."
    try:
        await query.edit_message_caption(caption=final_text, reply_markup=None)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.warning("Message not modified, skipping edit in admin_approve_failed_callback.")
            pass
        else:
            raise
    except Exception as e:
        logger.error(f"Error editing message in admin_approve_failed_callback: {e}")
        await query.message.reply_text(final_text)


async def admin_reject_failed_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin rejects a failed receipt - asks for rejection reason"""
    query = update.callback_query
    await query.answer("Please provide rejection reason...")
    
    admin_user = query.from_user
    if not is_admin_user(admin_user.id):
        await query.edit_message_caption(caption=error_message("admin_only"))
        return
    
    # Parse callback data
    prefix = config.CallbackPrefix.ADMIN_REJECT_FAILED
    data = query.data[len(prefix):]
    enrollment_ids_str, telegram_user_id_str = data.split("|")
    
    # Store in context for next message handler
    context.user_data["pending_failed_rejection_enrollments"] = enrollment_ids_str
    context.user_data["pending_failed_rejection_user"] = telegram_user_id_str
    context.user_data["awaiting_failed_rejection_reason"] = True
    
    prompt_text = f"❌ Rejecting enrollments {enrollment_ids_str} for user {telegram_user_id_str}.\n\n📝 Please send the rejection reason now (in Arabic or English):"
    
    try:
        await query.edit_message_caption(caption=prompt_text, reply_markup=None)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.warning("Message not modified, skipping edit in admin_reject_failed_callback.")
            pass
        else:
            raise
    except Exception as e:
        logger.error(f"Error editing message in admin_reject_failed_callback: {e}")
        await query.message.reply_text(prompt_text)


async def failed_rejection_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin sending rejection reason for failed receipt"""
    user_id = update.effective_user.id
    
    if not is_admin_user(user_id):
        return
    
    # Check if we're expecting a failed rejection reason
    if not context.user_data.get("awaiting_failed_rejection_reason"):
        return
    
    enrollment_ids_str = context.user_data.get("pending_failed_rejection_enrollments")
    telegram_user_id_str = context.user_data.get("pending_failed_rejection_user")
    
    if not enrollment_ids_str or not telegram_user_id_str:
        return
    
    reason = update.message.text
    enrollment_ids = [int(eid.strip()) for eid in enrollment_ids_str.split(",")]
    telegram_user_id = int(telegram_user_id_str)
    
    user_chat_id = None
    course_names = []
    
    with get_db() as session:
        for enrollment_id in enrollment_ids:
            enrollment = crud.get_enrollment_by_id(session, enrollment_id)
            if not enrollment:
                continue
            
            # Update enrollment to failed
            crud.update_enrollment_status(
                session,
                enrollment_id,
                PaymentStatus.FAILED,
                admin_notes=f"Rejected: {reason}"
            )
            
            # Update transaction if exists
            from database.models import Transaction
            transaction = session.query(Transaction).filter(
                Transaction.enrollment_id == enrollment_id
            ).order_by(Transaction.submitted_date.desc()).first()
            
            if transaction:
                crud.update_transaction(
                    session,
                    transaction.transaction_id,
                    status=TransactionStatus.REJECTED,
                    failure_reason=reason,
                    admin_reviewed=user_id
                )
            
            # Get user info
            user = enrollment.user
            user_chat_id = user.telegram_chat_id
            course = enrollment.course
            course_names.append(course.course_name)
        
        session.commit()
    
    # Notify user
    if user_chat_id:
        rejection_message = f"""
❌ **تم رفض دفعتك**

**السبب:** {reason}

الرجاء إرسال إيصال صحيح من قائمة "دوراتي".
"""
        try:
            await context.bot.send_message(
                chat_id=user_chat_id,
                text=rejection_message,
                parse_mode='Markdown'
            )
            await update.message.reply_text(
                f"❌ تم رفض التسجيلات {enrollment_ids_str}.\n\n**السبب:** {reason}\n\n✉️ تم إشعار المستخدم {telegram_user_id} ويمكنه المحاولة مرة أخرى.",
                reply_markup=admin_menu_keyboard(),
                parse_mode='Markdown'
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ تم رفض التسجيلات {enrollment_ids_str}.\n\n**السبب:** {reason}\n\n⚠️ فشل إشعار المستخدم.",
                reply_markup=admin_menu_keyboard(),
                parse_mode='Markdown'
            )
    else:
        await update.message.reply_text(
            f"❌ تم رفض التسجيلات {enrollment_ids_str}: {reason}",
            reply_markup=admin_menu_keyboard()
        )
    
    # Clear context
    context.user_data.pop("pending_failed_rejection_enrollments", None)
    context.user_data.pop("pending_failed_rejection_user", None)
    context.user_data.pop("awaiting_failed_rejection_reason", None)


async def send_daily_summary_report(context: ContextTypes.DEFAULT_TYPE):
    """Send daily summary report to admin chat"""
    from datetime import datetime, timedelta
    import pytz
    
    # Use Sudan timezone
    sudan_tz = pytz.timezone('Africa/Khartoum')
    
    # Calculate yesterday's date range in Sudan time
    # Calculate today's date range in Sudan time
    now_sudan = datetime.now(sudan_tz)
    today_start_sudan = now_sudan.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end_sudan = today_start_sudan + timedelta(days=1)

    # Convert to UTC for database queries (database stores in UTC)
    today_start = today_start_sudan.astimezone(pytz.UTC).replace(tzinfo=None)
    today_end = today_end_sudan.astimezone(pytz.UTC).replace(tzinfo=None)

    logger.info(f"Generating daily summary report for {today_start_sudan.strftime('%Y-%m-%d')}")

    
    try:
        with get_db() as session:
            # Get verified enrollments from today
            enrollments = crud.get_daily_verified_enrollments(session, today_start, today_end)
            
            # Format the report
            from utils.messages import daily_summary_report_message
            report_message = daily_summary_report_message(
                enrollments, 
                today_start_sudan.strftime('%Y-%m-%d')
            )
            
            # Send to admin chat
            await context.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=report_message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Daily summary report sent successfully. {len(enrollments)} enrollments reported.")
    
    except Exception as e:
        logger.error(f"Error sending daily summary report: {e}")
        # Send error notification to admin
        await context.bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=f"❌ Error generating daily report: {str(e)}"
        )

    
async def manual_daily_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual trigger for today's daily report (admin only) - uses Sudan time"""
    from datetime import datetime, timedelta
    import pytz
    
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    # Use Sudan timezone
    sudan_tz = pytz.timezone('Africa/Khartoum')
    
    # Get today's date range in Sudan time
    now_sudan = datetime.now(sudan_tz)
    today_start_sudan = now_sudan.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end_sudan = today_start_sudan + timedelta(days=1)
    
    # Convert to UTC for database queries
    today_start = today_start_sudan.astimezone(pytz.UTC).replace(tzinfo=None)
    today_end = today_end_sudan.astimezone(pytz.UTC).replace(tzinfo=None)
    
    logger.info(f"Generating manual daily summary report for {today_start_sudan.strftime('%Y-%m-%d')} (Sudan Time)")
    
    try:
        with get_db() as session:
            # Get verified enrollments from today
            enrollments = crud.get_daily_verified_enrollments(session, today_start, today_end)
            
            # Format the report
            from utils.messages import daily_summary_report_message
            report_message = daily_summary_report_message(
                enrollments, 
                today_start_sudan.strftime('%Y-%m-%d')
            )
            
            # Send to the chat
            await update.message.reply_text(report_message, parse_mode='Markdown')
            
            logger.info(f"Manual daily summary report sent. {len(enrollments)} enrollments reported.")
    
    except Exception as e:
        logger.error(f"Error generating manual daily report: {e}")
        await update.message.reply_text(f"❌ Error generating report: {str(e)}")

async def set_certificate_price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin command to set certificate price for a course
    Usage: /setcert <course_id> <price>
    Example: /setcert 1 2000
    """
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    try:
        # Parse command: /setcert 1 2000
        args = context.args
        if len(args) != 2:
            await update.message.reply_text(
                "❌ Usage: /setcert <course_id> <price>\n"
                "Example: /setcert 1 2000"
            )
            return
        
        course_id = int(args[0])
        certificate_price = float(args[1])
        
        with get_db() as session:
            from database.models import Course
            course = session.query(Course).filter(Course.course_id == course_id).first()
            
            if not course:
                await update.message.reply_text(f"❌ Course {course_id} not found.")
                return
            
            course.certificate_price = certificate_price
            course.certificate_available = certificate_price > 0
            session.commit()
            
            status = "[translate:متاحة]" if certificate_price > 0 else "[translate:غير متاحة]"
            await update.message.reply_text(
                f"✅ Certificate price updated!\n\n"
                f"📚 Course: {course.course_name}\n"
                f"📜 Certificate Price: {certificate_price} SDG\n"
                f"Status: {status}"
            )
    
    except ValueError:
        await update.message.reply_text("❌ Invalid numbers. Use: /setcert <course_id> <price>")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
