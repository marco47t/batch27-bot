
"""
Telegram group join requests handler
"""
from telegram import Update
from telegram.ext import ContextTypes
from database import get_db
import logging

logger = logging.getLogger(__name__)


async def group_join_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle join requests - auto-approve verified students"""
    join_request = update.chat_join_request
    user = join_request.from_user
    chat = join_request.chat
    
    logger.info(f"Join request from {user.id} ({user.username}) to group {chat.id} ({chat.title})")
    
    with get_db() as session:
        # --- FIX START ---
        # We need all three models for this check
        from database.models import Course, Enrollment, PaymentStatus, User
        
        # 1. Find the course linked to this group ID
        course = session.query(Course).filter(
            Course.telegram_group_id == str(chat.id)
        ).first()
        
        if not course:
            logger.warning(f"No course linked to group {chat.id}. Declining join request.")
            await join_request.decline()
            return
        
        # 2. Find the internal database user record using the Telegram user ID
        db_user = session.query(User).filter(User.telegram_user_id == user.id).first()

        if not db_user:
            logger.info(f"Declined {user.username} ({user.id}) - user has never started the bot and is not in the database.")
            await join_request.decline()
            return

        # 3. Check for a VERIFIED enrollment using the INTERNAL database user ID
        enrollment = session.query(Enrollment).filter(
            Enrollment.user_id == db_user.user_id,  # Use the correct internal ID
            Enrollment.course_id == course.course_id,
            Enrollment.payment_status == PaymentStatus.VERIFIED
        ).first()
        
        # --- FIX END ---
        
        if enrollment:
            # Auto-approve if a verified enrollment is found
            await join_request.approve()
            logger.info(f"✅ Auto-approved {user.username} ({user.id}) to {course.course_name}")
            
            # Send a welcome message to the user in their private chat
            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=f"✅ **Welcome to {course.course_name}!**\n\n"
                         f"Your request to join the group has been approved.\n"
                         f"Enjoy the course! 🎓",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Could not send welcome message to user {user.id}: {e}")
        else:
            # Decline if no verified enrollment is found
            await join_request.decline()
            logger.info(f"❌ Declined {user.username} ({user.id}) - not enrolled or payment not verified for {course.course_name}")
            
            # Inform the user why they were declined
            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=f"❌ **Join Request Declined**\n\n"
                         f"Your request to join the group for **{course.course_name}** was declined "
                         f"because a verified payment was not found for your account.\n\n"
                         f"Please use /start to check your enrollment status under 'My Courses'.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Could not send decline message to user {user.id}: {e}")

# Note: The old chat_join_request_handler is redundant if group_join_handler is this robust.
# I've removed it to avoid confusion and kept the more detailed and correct group_join_handler.