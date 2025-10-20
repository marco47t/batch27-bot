"""
Support/Contact Admin System
Allows users to send messages to admins
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import crud, get_db
from utils.helpers import send_admin_notification
from utils.keyboards import back_to_main_keyboard
import config
import logging

logger = logging.getLogger(__name__)

# Conversation states
AWAITING_SUPPORT_MESSAGE = 1


async def contact_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /contact command - Start conversation to contact admin
    """
    user = update.effective_user
    
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

❌ لإلغاء الإرسال اكتب: /cancel
"""
    
    await update.message.reply_text(
        message,
        parse_mode='Markdown',
        reply_markup=back_to_main_keyboard()
    )
    
    # Set state to wait for message
    context.user_data['awaiting_support_message'] = True
    return AWAITING_SUPPORT_MESSAGE


async def receive_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Receive and forward user's message to admin
    """
    if not context.user_data.get('awaiting_support_message'):
        return ConversationHandler.END
    
    user = update.effective_user
    message = update.message
    
    # Get user info from database
    with get_db() as session:
        db_user = crud.get_user_by_telegram_id(session, user.id)
        
        if db_user:
            user_display = f"{db_user.full_name} (ID: {db_user.user_id})"
        else:
            user_display = f"{user.first_name} {user.last_name or ''} (Telegram: {user.id})"
    
    # Build admin notification
    admin_message = f"""
📩 **رسالة جديدة من مستخدم / New User Message**

👤 **المستخدم / User:** {user_display}
📱 **Telegram ID:** {user.id}
🔗 **Profile:** tg://user?id={user.id}

📝 **الرسالة / Message:**
"""
    
    try:
        # Forward message to admin chat
        if message.text:
            # Text message
            await context.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=admin_message + f"\n{message.text}",
                parse_mode='Markdown'
            )
        
        elif message.photo:
            # Photo with caption
            photo = message.photo[-1]  # Get highest resolution
            caption = message.caption or "(No caption)"
            await context.bot.send_photo(
                chat_id=config.ADMIN_CHAT_ID,
                photo=photo.file_id,
                caption=admin_message + f"\n{caption}",
                parse_mode='Markdown'
            )
        
        elif message.document:
            # Document
            await context.bot.send_document(
                chat_id=config.ADMIN_CHAT_ID,
                document=message.document.file_id,
                caption=admin_message,
                parse_mode='Markdown'
            )
        
        else:
            # Other message types
            await context.bot.forward_message(
                chat_id=config.ADMIN_CHAT_ID,
                from_chat_id=message.chat_id,
                message_id=message.message_id
            )
            await context.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=admin_message,
                parse_mode='Markdown'
            )
        
        # Confirm to user
        await message.reply_text(
            "✅ **تم إرسال رسالتك للإدارة**\n"
            "سيتم الرد عليك في أقرب وقت.\n\n"
            "✅ **Message sent to administration**\n"
            "You will receive a response soon.",
            parse_mode='Markdown',
            reply_markup=back_to_main_keyboard()
        )
        
        logger.info(f"✅ Support message from user {user.id} forwarded to admin")
        
    except Exception as e:
        logger.error(f"Failed to forward support message: {e}")
        await message.reply_text(
            "❌ حدث خطأ في إرسال الرسالة. يرجى المحاولة لاحقاً.\n"
            "❌ Error sending message. Please try again later.",
            reply_markup=back_to_main_keyboard()
        )
    
    # Clear state
    context.user_data.pop('awaiting_support_message', None)
    return ConversationHandler.END


async def cancel_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancel support message conversation
    """
    context.user_data.pop('awaiting_support_message', None)
    
    await update.message.reply_text(
        "❌ **تم إلغاء الإرسال**\n"
        "❌ **Cancelled**",
        parse_mode='Markdown',
        reply_markup=back_to_main_keyboard()
    )
    
    return ConversationHandler.END
