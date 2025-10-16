"""
Admin Registration Handler - Password-based admin registration
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import crud, get_db
import config
import logging

logger = logging.getLogger(__name__)

# Conversation state
AWAITING_PASSWORD = 1

async def register_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start admin registration process - PRIVATE CHAT ONLY"""
    user = update.effective_user
    chat = update.effective_chat
    
    # CHECK: Only allow in private chat
    if chat.type != 'private':
        await update.message.reply_text(
            "⚠️ Admin registration must be done in private chat.\n\n"
            "Click here to continue: @YourBotUsername",
            reply_to_message_id=update.message.message_id
        )
        return ConversationHandler.END
    
    # Check if already admin
    with get_db() as session:
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        session.commit()
        
        if db_user.is_admin:
            await update.message.reply_text("✅ You are already an admin!")
            return ConversationHandler.END
    
    await update.message.reply_text(
        "🔐 **Admin Registration**\n\n"
        "Please enter the admin password:\n\n"
        "Send /cancel to abort.",
        parse_mode='Markdown'
    )
    
    return AWAITING_PASSWORD


async def receive_admin_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify password and grant admin access"""
    user = update.effective_user
    password = update.message.text.strip()
    
    # Delete the message with password for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete password message: {e}")
    
    # Verify password
    if password == config.ADMIN_REGISTRATION_PASSWORD:
        with get_db() as session:
            db_user = crud.get_or_create_user(
                session,
                telegram_user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            
            db_user.is_admin = True
            session.commit()
            
            logger.info(f"✅ New admin registered: {user.id} - {user.username}")
            
            await context.bot.send_message(
                chat_id=user.id,
                text=f"✅ **Admin Access Granted!**\n\n"
                     f"Welcome, {user.first_name}!\n\n"
                     f"You now have admin privileges.\n\n"
                     f"**Commands:**\n"
                     f"• /admin - Admin panel\n"
                     f"• /addcourse - Add new course\n"
                     f"• /listcourses - List all courses\n"
                     f"• /editcourse - Edit a course\n"
                     f"• /togglecourse - Enable/disable course\n"
                     f"• /deletecourse - Delete a course",
                parse_mode='Markdown'
            )
            
            return ConversationHandler.END
    else:
        await context.bot.send_message(
            chat_id=user.id,
            text="❌ **Incorrect Password**\n\n"
                 "Admin access denied.\n"
                 "Use /register to try again.",
            parse_mode='Markdown'
        )
        
        logger.warning(f"⚠️ Failed admin registration attempt: {user.id} - {user.username}")
        return ConversationHandler.END


async def cancel_admin_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel admin registration"""
    await update.message.reply_text("❌ Admin registration cancelled.")
    return ConversationHandler.END
