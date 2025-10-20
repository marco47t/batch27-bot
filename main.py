# main.py

"""Course Registration Telegram Bot - Main Application"""
from venv import logger
import os
import sys
from database import migrate_add_amount_paid
from datetime import timedelta
import logging
from telegram import Update
from telegram.ext import (
    filters, 
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    ChatJoinRequestHandler, 
    ConversationHandler,
    ContextTypes
)
from handlers import (
    menu_handlers,
    course_handlers,
    group_handlers,
    payment_handlers,
    admin_handlers,
    admin_course_management,
    admin_registration,
    group_registration,
    admin_receipt_management,
    admin_export,
    admin_broadcast,
    admin_search,
    student_preferences,
    student_reviews,
    admin_reviews,
    admin_pending_registrations,
)
from handlers.course_handlers import handle_legal_name_during_registration
from handlers.support_handlers import contact_admin_callback, contact_admin_command, handle_support_message
from handlers.menu_handlers import contact_admin_callback
from database import crud, get_db, init_db
from utils.helpers import handle_error
import config

log_dir = os.path.dirname(os.path.abspath(__file__))
app_log = os.path.join(log_dir, 'bot.log')
error_log = os.path.join(log_dir, 'bot_error.log')

# Create handlers
handlers = [logging.StreamHandler(sys.stdout)]  # Always log to console

# Try to add file handlers
try:
    handlers.append(logging.FileHandler(app_log, mode='a'))
    handlers.append(logging.FileHandler(error_log, mode='a'))
except PermissionError:
    print(f"Warning: Could not write to log files in {log_dir}")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, config.LOG_LEVEL.upper()),
    handlers=handlers
)

def run_database_migration():
    """Run database migration to fix BigInteger issue"""
    from sqlalchemy import create_engine, text, inspect
    import config
    
    try:
        engine = create_engine(config.DATABASE_URL)
        inspector = inspect(engine)
        
        # Check current column type
        columns = inspector.get_columns('users')
        telegram_user_id_col = next((col for col in columns if col['name'] == 'telegram_user_id'), None)
        
        if telegram_user_id_col and str(telegram_user_id_col['type']) == 'INTEGER':
            logger.info("🔧 Running BigInteger migration...")
            
            with engine.connect() as connection:
                trans = connection.begin()
                try:
                    # Change telegram_user_id to BIGINT
                    connection.execute(text(
                        "ALTER TABLE users ALTER COLUMN telegram_user_id TYPE BIGINT"
                    ))
                    connection.execute(text(
                        "ALTER TABLE users ALTER COLUMN telegram_chat_id TYPE BIGINT"
                    ))
                    trans.commit()
                    logger.info("✅ BigInteger migration completed!")
                except Exception as e:
                    trans.rollback()
                    logger.error(f"❌ Migration failed: {e}")
        else:
            logger.info("✅ Database already using BigInteger")
            
    except Exception as e:
        logger.error(f"❌ Migration check failed: {e}")


async def send_review_prompts(context: ContextTypes.DEFAULT_TYPE):
    """Automatically send review prompts for completed courses"""
    from datetime import datetime, timedelta
    import pytz
    
    logger.info("Running auto review prompt check...")
    
    sudan_tz = pytz.timezone('Africa/Khartoum')
    now = datetime.now(sudan_tz).replace(tzinfo=None)
    six_hours_ago = now - timedelta(hours=6)  # ✅ Changed from 24hrs to 6hrs
    
    with get_db() as session:
        # Find courses that ended in the LAST 6 HOURS (prevents duplicates)
        from database.models import Course, Enrollment, CourseReview, PaymentStatus
        
        ended_courses = session.query(Course).filter(
            Course.end_date.isnot(None),
            Course.end_date >= six_hours_ago,  # ✅ Only last 6 hours
            Course.end_date < now
        ).all()
        
        if not ended_courses:
            logger.info("No courses ended in the last 6 hours")
            return
        
        logger.info(f"Found {len(ended_courses)} courses that ended in last 6 hours")
        
        for course in ended_courses:
            # Get all verified students in this course
            enrollments = session.query(Enrollment).filter(
                Enrollment.course_id == course.course_id,
                Enrollment.payment_status == PaymentStatus.VERIFIED
            ).all()
            
            for enrollment in enrollments:
                # Check if already reviewed
                existing_review = session.query(CourseReview).filter(
                    CourseReview.enrollment_id == enrollment.enrollment_id
                ).first()
                
                if existing_review:
                    continue  # Already reviewed
                
                # Check notification preferences
                prefs = crud.get_or_create_notification_preferences(session, enrollment.user_id)
                if not prefs.broadcast_messages:
                    continue  # User doesn't want notifications
                
                # Send review prompt
                try:
                    message_text = (
                        f"⭐ **Course Completed!**\n\n"
                        f"🎓 {course.course_name}\n\n"
                        f"How was your experience? We'd love your feedback!\n\n"
                        f"Type /ratecourse to leave a review. Your feedback helps us improve! 🙏"
                    )
                    
                    await context.bot.send_message(
                        chat_id=enrollment.user.telegram_user_id,
                        text=message_text,
                        parse_mode='Markdown'
                    )
                    
                    logger.info(f"Sent review prompt to user {enrollment.user_id} for course {course.course_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to send review prompt to user {enrollment.user_id}: {e}")


def run_migrations():
    """Run database migrations on startup"""
    from database.models import Base
    from database.session import engine
    
    try:
        Base.metadata.create_all(engine)
        logger.info("✅ Database tables created/updated successfully")
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")

def ensure_admin_users():
    """Ensure users from ADMIN_USER_IDS are marked as admin"""
    from database import get_db
    from database.models import User
    import config
    
    if not config.ADMIN_USER_IDS:
        logger.warning("No ADMIN_USER_IDS configured")
        return
    
    logger.info(f"Checking admin users: {config.ADMIN_USER_IDS}")
    
    with get_db() as session:
        for user_id in config.ADMIN_USER_IDS:
            try:
                # Try to get existing user
                user = session.query(User).filter_by(telegram_user_id=user_id).first()
                if user:
                    if not user.is_admin:
                        user.is_admin = True
                        session.commit()
                        logger.info(f"✅ Granted admin access to existing user {user_id}")
                    else:
                        logger.info(f"User {user_id} is already admin")
                else:
                    logger.info(f"User {user_id} not in database yet - will be granted admin on first /start")
            except Exception as e:
                logger.error(f"Error granting admin to {user_id}: {e}")
                session.rollback()


def main():
    """Main bot application"""
    logger.info("Starting Course Registration Bot...")
    
    # Initialize database
    logger.info("Initializing database...")
    init_db()
    run_database_migration()
    logger.info("Database initialized successfully!")
    # Ensure admin users are configured
    
    logger.info("Checking admin configuration...")
    ensure_admin_users()  # ADD THIS LINE
    logger.info("Admin configuration complete!")
    
    # Create application
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # ==========================
    # COMMAND HANDLERS
    # ==========================
    application.add_handler(CommandHandler("start", menu_handlers.start_command))
    application.add_handler(CommandHandler("admin", admin_handlers.admin_command))
    application.add_handler(CommandHandler("pending_registrations", admin_pending_registrations.admin_pending_registrations_command))  # NEW

    # ADMIN COURSE MANAGEMENT COMMANDS
    application.add_handler(CommandHandler("listcourses", admin_course_management.list_courses_command))
    application.add_handler(CommandHandler("togglecourse", admin_course_management.toggle_course_command))
    application.add_handler(CommandHandler("deletecourse", admin_course_management.delete_course_command))
    
    # ==========================
    # CONVERSATION HANDLERS
    # ==========================
    
    # Admin Registration Conversation
    admin_reg_conv = ConversationHandler(
        entry_points=[CommandHandler("register", admin_registration.register_admin_command)],
        states={
            admin_registration.AWAITING_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_registration.receive_admin_password)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_registration.cancel_admin_registration)],
        per_message=False,
        allow_reentry=True,
        name="admin_registration"
    )
    application.add_handler(admin_reg_conv)
    
    # Add Course Conversation
    addcourse_conv = ConversationHandler(
        entry_points=[CommandHandler("addcourse", admin_course_management.add_course_command)],
            states={
                admin_course_management.COURSE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_course_management.course_name_input)],
                admin_course_management.COURSE_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_course_management.course_description_input)],
                admin_course_management.COURSE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_course_management.course_price_input)],
                admin_course_management.COURSE_MAX_STUDENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_course_management.course_max_students_input)],
                admin_course_management.COURSE_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_course_management.course_start_date_input)],
                admin_course_management.COURSE_END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_course_management.course_end_date_input)],
                admin_course_management.COURSE_REG_OPEN_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_course_management.course_reg_open_date_input)],
                admin_course_management.COURSE_REG_CLOSE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_course_management.course_reg_close_date_input)],
                admin_course_management.COURSE_CONFIRM: [CallbackQueryHandler(admin_course_management.course_confirm_callback)],
            },
        fallbacks=[CommandHandler("cancel", admin_course_management.cancel_course_creation)],
        per_message=False,
        name="add_course"
    )
    application.add_handler(addcourse_conv)
    
    # Edit Course Conversation
    editcourse_conv = ConversationHandler(
        entry_points=[CommandHandler("editcourse", admin_course_management.edit_course_command)],
        states={
            admin_course_management.EDIT_SELECT_COURSE: [
                CallbackQueryHandler(admin_course_management.edit_select_course_callback)
            ],
            admin_course_management.EDIT_SELECT_FIELD: [
                CallbackQueryHandler(admin_course_management.edit_select_field_callback)
            ],
            admin_course_management.EDIT_INPUT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_course_management.edit_input_value)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_course_management.cancel_course_creation)],
        per_message=False,
        name="edit_course"
    )
    application.add_handler(editcourse_conv)
    
    # ==========================
    # MESSAGE HANDLERS (ReplyKeyboard Buttons) - FIXED
    # ==========================
    application.add_handler(MessageHandler(
        filters.Text(["1- الدورات المتاحة 📚"]), 
        menu_handlers.handle_courses_menu_message

    ))
    application.add_handler(MessageHandler(
        filters.Text(["2- دوراتي 📋"]), 
        menu_handlers.handle_my_courses_from_message
    ))
    application.add_handler(MessageHandler(
        filters.Text(["3- حول البوت ℹ️"]), 
        menu_handlers.handle_about_bot_message
    ))

    application.add_handler(MessageHandler(
        filters.Regex("^3- تقييم دورة ⭐$"), 
        menu_handlers.rate_course_menu_handler
    ))

    application.add_handler(MessageHandler(
        filters.Regex("^4- الإشعارات 🔔$"), 
        menu_handlers.preferences_menu_handler
    ))
    
    # ==========================
    # CALLBACK QUERY HANDLERS
    # ==========================
    
    # Main Menu & About
    application.add_handler(CallbackQueryHandler(
        menu_handlers.back_to_main_callback,  # ✅ CORRECT
        pattern=f'^{config.CallbackPrefix.BACK_MAIN}'
    ))
    application.add_handler(CallbackQueryHandler(
        menu_handlers.about_bot_callback, 
        pattern='about_bot'
    ))
    
    # Courses Flow
    application.add_handler(CallbackQueryHandler(
        menu_handlers.courses_menu_callback, 
        pattern='courses_menu'
    ))
    application.add_handler(CallbackQueryHandler(
        course_handlers.course_details_menu_callback, 
        pattern='course_details_menu'
    ))
    application.add_handler(CallbackQueryHandler(
        course_handlers.view_cart_callback, 
        pattern='view_cart'
    ))
    application.add_handler(CallbackQueryHandler(
        course_handlers.course_detail_callback, 
        pattern=r'^course_detail_'
    ))
    application.add_handler(CallbackQueryHandler(
        course_handlers.course_selection_menu_callback, 
        pattern='course_selection_menu'
    ))
    application.add_handler(CallbackQueryHandler(
        course_handlers.course_select_callback, 
        pattern=r'^course_select_'
    ))
    application.add_handler(CallbackQueryHandler(
        course_handlers.course_deselect_callback, 
        pattern=r'^course_deselect_'
    ))
    application.add_handler(CallbackQueryHandler(
        course_handlers.clear_cart_callback, 
        pattern='clear_cart'
    ))
    application.add_handler(CallbackQueryHandler(
        course_handlers.confirm_cart_callback, 
        pattern='confirm_cart'
    ))
    application.add_handler(CallbackQueryHandler(
        payment_handlers.proceed_to_payment_callback, 
        pattern='proceed_payment'
    ))
    application.add_handler(CallbackQueryHandler(
        menu_handlers.courses_menu_callback, 
        pattern=f'^{config.CallbackPrefix.BACK_COURSES}'
    ))
    
    # My Courses Payment Flow
    application.add_handler(CallbackQueryHandler(
        menu_handlers.my_courses_callback, 
        pattern=f'^{config.CallbackPrefix.MY_COURSES}'
    ))
    application.add_handler(CallbackQueryHandler(
        menu_handlers.my_course_select_deselect_callback, 
        pattern=r'^my_course_(select|deselect)_'
    ))
    application.add_handler(CallbackQueryHandler(
        menu_handlers.proceed_to_pay_selected_pending_callback, 
        pattern='pay_selected_pending'
    ))
    application.add_handler(CallbackQueryHandler(
        menu_handlers.cancel_selected_pending_callback,
        pattern='cancel_selected_pending'
    ))
    

    # Add these handlers
    application.add_handler(CallbackQueryHandler(menu_handlers.my_course_detail_callback, pattern="^my_course_detail_"))
    application.add_handler(CallbackQueryHandler(menu_handlers.complete_payment_callback, pattern="^complete_payment_"))

    # Admin Flow
    application.add_handler(CallbackQueryHandler(
        admin_handlers.admin_stats_callback, 
        pattern='admin_stats'
    ))
    application.add_handler(CallbackQueryHandler(
        admin_handlers.admin_pending_callback, 
        pattern='admin_pending'
    ))
    application.add_handler(CallbackQueryHandler(admin_pending_registrations.admin_pending_registrations_callback, pattern="^admin_pending_registrations$"))  # NEW
    application.add_handler(CallbackQueryHandler(admin_pending_registrations.admin_refresh_pending_registrations_callback, pattern="^admin_refresh_pending_registrations$"))  # NEW

# ✨ NEW HANDLERS MUST COME FIRST (more specific patterns)
    application.add_handler(CallbackQueryHandler(
        admin_handlers.admin_approve_failed_callback,
        pattern=f"^{config.CallbackPrefix.ADMIN_APPROVE_FAILED}"
    ))

    application.add_handler(CallbackQueryHandler(
        admin_handlers.admin_reject_failed_callback,
        pattern=f"^{config.CallbackPrefix.ADMIN_REJECT_FAILED}"
    ))
    application.add_handler(CallbackQueryHandler(
        admin_handlers.admin_approve_callback, 
        pattern=r'^admin_approve_'
    ))
    application.add_handler(CallbackQueryHandler(
        admin_handlers.admin_reject_callback, 
        pattern=r'^admin_reject_'
    ))
    
    # Admin Course Management Callbacks
    application.add_handler(CallbackQueryHandler(
        admin_course_management.delete_course_callback, 
        pattern=r'^delete_course_'
    ))
    application.add_handler(CallbackQueryHandler(
        admin_course_management.delete_course_callback, 
        pattern='cancel_delete'
    ))
    application.add_handler(CallbackQueryHandler(
        admin_course_management.toggle_course_callback, 
        pattern=r'^toggle_course_'
    ))
    application.add_handler(CallbackQueryHandler(
        admin_course_management.toggle_course_callback, 
        pattern='cancel_toggle'
    ))
    application.add_handler(CommandHandler('dailyreport', admin_handlers.manual_daily_report_command))

    receipt_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('getreceipt', admin_receipt_management.get_receipt_command),
            CommandHandler('receiptsdate', admin_receipt_management.receipts_date_command),
        ],
        states={
            admin_receipt_management.RECEIPT_USER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receipt_management.receipt_user_id_input)
            ],
            admin_receipt_management.RECEIPT_DATE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receipt_management.receipt_date_input)
            ],
        },
        fallbacks=[CommandHandler('cancel', admin_receipt_management.cancel_receipt_search)],
    )
    application.add_handler(receipt_conv_handler)

    # Simple command handlers
    application.add_handler(CommandHandler('receiptstoday', admin_receipt_management.receipts_today_command))
    # ==========================
    # ADMIN SUPPORT HANDLERS
    # ==========================
    application.add_handler(CallbackQueryHandler(contact_admin_callback, pattern="^contact_admin$"))

    # Add command
    application.add_handler(CommandHandler("contact", contact_admin_command))

    # IMPORTANT: Add this BEFORE your other message handlers
    # This checks if user is in support mode first
    async def support_message_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check and handle support messages first"""
        if context.user_data.get('awaiting_support_message'):
            await handle_support_message(update, context)
            return  # Stop processing other handlers

    # Add this handler with high priority (add it early in your handler list)
    application.add_handler(
        MessageHandler(
            filters.TEXT | filters.PHOTO | filters.Document.ALL | filters.VOICE, 
            support_message_filter
        ),
        group=-1  # High priority - runs before other message handlers
    )
    # ==========================
    # FILE/IMAGE HANDLERS
    # ==========================
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.IMAGE, 
        payment_handlers.receipt_upload_message_handler
    ))

    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_legal_name_during_registration
    ), group=0)  # Higher priority

    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.User(config.ADMIN_USER_IDS), 
        admin_handlers.rejection_reason_message_handler
    ))


    # GROUP REGISTRATION COMMAND
    # ==========================
    application.add_handler(CommandHandler("register_group", group_registration.register_group_command))
    
    # Group registration callback
    application.add_handler(CallbackQueryHandler(
        group_registration.link_group_callback, 
        pattern=r'^link_group_'
    ))
    application.add_handler(CallbackQueryHandler(
        group_registration.link_group_callback, 
        pattern='cancel_link_group'
    ))
    
    # ==========================
    # GROUP JOIN REQUEST HANDLER
    # ==========================
    application.add_handler(ChatJoinRequestHandler(group_handlers.group_join_handler))
    
    # ==========================
    # ERROR HANDLER
    # ==========================
    async def error_handler(update, context):
        logger.error('Update "%s" caused error "%s"', update, context.error, exc_info=context.error)
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text("حدث خطأ. الرجاء المحاولة لاحقاً.")
            except:
                pass
    


    application.add_error_handler(error_handler)
    # ========== SCHEDULE DAILY SUMMARY REPORT ==========
    from datetime import time
    import pytz

    # Check if job_queue is available (requires python-telegram-bot[job-queue])
    if application.job_queue:
        # Schedule daily report at 21:00 EET (Eastern European Time)
        sudan_tz = pytz.timezone('Africa/Khartoum')  # Sudan timezone (UTC+2)
        
        application.job_queue.run_daily(
            admin_handlers.send_daily_summary_report,
            time=time(hour=21, minute=0, second=0, tzinfo=sudan_tz),  # 9:00 PM EET
            name='daily_summary_report'
        )
        application.job_queue.run_repeating(
            send_review_prompts,
            interval=timedelta(hours=6),  # Check every 6 hours
            first=timedelta(seconds=60),   # Start 1 minute after bot starts
            name='auto_review_prompts'
        )
        logger.info("Auto review prompts scheduled (runs every 6 hours)")
        
        logger.info("Daily summary report scheduled for 21:00 Sudan Time (CAT)")
    else:
        logger.warning("JobQueue not available. Install python-telegram-bot[job-queue] to enable daily reports.")

    # ========================
    # Export Handlers
    # ========================
    # ==========================
    # RUN BOT
    # ==========================
    application.add_handler(CommandHandler('exportenrollments', admin_export.export_enrollments_command))
    application.add_handler(CommandHandler('exporttransactions', admin_export.export_transactions_command))
    application.add_handler(CommandHandler('dashboard', admin_export.generate_dashboard_command))
    
    # Broadcast conversation handler
    broadcast_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('broadcast', admin_broadcast.broadcast_command)],
        states={
            admin_broadcast.BROADCAST_TYPE: [
                CallbackQueryHandler(admin_broadcast.broadcast_type_callback)
            ],
            admin_broadcast.COURSE_SELECT: [
                CallbackQueryHandler(admin_broadcast.course_select_callback)
            ],
            admin_broadcast.BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast.broadcast_message_input)
            ],
            admin_broadcast.CONFIRM_BROADCAST: [
                CallbackQueryHandler(admin_broadcast.confirm_broadcast_callback)
            ],
        },
        fallbacks=[CommandHandler('cancel', admin_broadcast.cancel_broadcast)],
    )
    application.add_handler(broadcast_conv_handler)

    # Student search conversation handler
    search_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('searchstudent', admin_search.search_student_command)],
        states={
            admin_search.SEARCH_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_search.search_input_handler)
            ],
        },
        fallbacks=[CommandHandler('cancel', admin_search.cancel_search)],
    )
    application.add_handler(search_conv_handler)
    
    review_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('ratecourse', student_reviews.rate_course_command)],
        states={
            student_reviews.REVIEW_COURSE_SELECT: [
                CallbackQueryHandler(student_reviews.review_course_select_callback)
            ],
            student_reviews.REVIEW_RATING: [
                CallbackQueryHandler(student_reviews.review_rating_callback)
            ],
            student_reviews.REVIEW_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, student_reviews.review_comment_input),
                CallbackQueryHandler(student_reviews.skip_comment_callback)
            ],
        },
        fallbacks=[CommandHandler('cancel', student_reviews.cancel_review)],
    )
    application.add_handler(review_conv_handler)



    # Admin review viewing
    application.add_handler(CommandHandler('viewreviews', admin_reviews.view_reviews_command))
    application.add_handler(CommandHandler('exportreviews', admin_reviews.export_reviews_command))

    # Course reviews conversation handler
    course_reviews_conv = ConversationHandler(
        entry_points=[CommandHandler('coursereviews', admin_reviews.course_reviews_command)],
        states={
            admin_reviews.COURSE_SELECT: [
                CallbackQueryHandler(admin_reviews.course_select_callback)
            ],
        },
        fallbacks=[CommandHandler('cancel', admin_reviews.cancel_review_view)],
    )
    application.add_handler(course_reviews_conv)

    # Student preferences conversation handler
    preferences_conv = ConversationHandler(
        entry_points=[CommandHandler('preferences', student_preferences.preferences_command)],
        states={
            student_preferences.PREFERENCE_SELECT: [
                CallbackQueryHandler(student_preferences.preference_toggle_callback)
            ],
        },
        fallbacks=[CommandHandler('cancel', student_preferences.cancel_preferences)],
    )
    application.add_handler(preferences_conv)

    logger.info("Bot started successfully! 🚀")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
