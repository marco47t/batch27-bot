"""
Utility helper functions
"""
import os
import logging
from typing import Optional
from datetime import datetime
from telegram import Update, User as TelegramUser
from telegram.ext import ContextTypes

import config

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, config.LOG_LEVEL.upper())
)
logger = logging.getLogger(__name__)

def get_user_info(update: Update) -> Optional[TelegramUser]:
    """Extract user information from update"""
    if update.effective_user:
        return update.effective_user
    return None

def get_chat_id(update: Update) -> Optional[int]:
    """Get chat ID from update"""
    if update.effective_chat:
        return update.effective_chat.id
    return None

def is_admin_user(user_id: int) -> bool:
    """Check if user is an admin - checks BOTH config AND database"""
    # First check config (always admin if in ADMIN_USER_IDS)
    if config.is_admin(user_id):
        return True
    
    # Then check database
    from database import get_db
    from database.models import User
    
    try:
        with get_db() as session:
            user = session.query(User).filter_by(telegram_user_id=user_id).first()
            if user and user.is_admin:
                return True
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}")
    
    return False


def save_receipt_image(file_path: str, user_id: int, timestamp: datetime = None) -> str:
    """Generate unique filename for receipt image"""
    if timestamp is None:
        timestamp = datetime.now()
    
    filename = f"receipt_{user_id}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
    full_path = os.path.join(config.RECEIPTS_DIR, filename)
    
    return full_path

def format_currency(amount: float) -> str:
    """Format currency amount"""
    return f"${amount:.2f}"

def log_user_action(user_id: int, action: str, details: str = ""):
    """Log user actions for debugging"""
    logger.info(f"User {user_id}: {action} {details}")

def extract_course_id_from_callback(callback_data: str, prefix: str) -> Optional[int]:
    """Extract course ID from callback data"""
    try:
        if callback_data.startswith(prefix):
            return int(callback_data[len(prefix):])
    except (ValueError, IndexError):
        pass
    return None

def safe_int_conversion(value: str) -> Optional[int]:
    """Safely convert string to integer"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
 
def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to specified length"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

async def send_admin_notification(context: ContextTypes.DEFAULT_TYPE, message: str):
    """Send notification to admin chat"""
    try:
        await context.bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=f"🔔 **Admin Notification**\n\n{message}",
        )
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")

def get_user_display_name(user: TelegramUser) -> str:
    """Get user's display name"""
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    elif user.first_name:
        return user.first_name
    elif user.username:
        return f"@{user.username}"
    else:
        return f"User {user.id}"

def validate_receipt_file(file_obj) -> bool:
    """Validate uploaded receipt file"""
    if not file_obj:
        return False
    
    # Check file size (max 10MB)
    if hasattr(file_obj, 'file_size') and file_obj.file_size > 10 * 1024 * 1024:
        return False
    
    # Check file type by extension or mime type
    valid_extensions = ['.jpg', '.jpeg', '.png', '.pdf']
    if hasattr(file_obj, 'file_path'):
        file_ext = os.path.splitext(file_obj.file_path)[1].lower()
        return file_ext in valid_extensions
    
    return True

async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE, error_msg: str):
    """Handle and log errors consistently"""
    logger.error(f"Error in {update.effective_user.id if update.effective_user else 'unknown'}: {error_msg}")
    
    try:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                text=f"❌ {error_msg}",
                reply_markup=None
            )
        else:
            await update.message.reply_text(f"❌ {error_msg}")
    except Exception as e:
        logger.error(f"Failed to send error message: {e}")

def clean_callback_data(data: str) -> str:
    """Clean and validate callback data"""
    if not data:
        return ""
    
    # Telegram callback data is limited to 64 bytes
    if len(data.encode('utf-8')) > 64:
        return data[:60] + "..."
    
    return data
