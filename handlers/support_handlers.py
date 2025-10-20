"""
Support/Contact Admin System - Simplified
"""

from telegram import Update
from telegram.ext import ContextTypes
from database import crud, get_db
from utils.keyboards import back_to_main_keyboard
import config
import logging

logger = logging.getLogger(__name__)


async def contact_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle contact admin button from main menu"""
    query = update.callback_query
    await query.answer()
    
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
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=back_to_main_keyboard()
    )
    
    # Set flag in user data
    context.user_data['awaiting_support_message'] = True
    logger.info(f"User {query.from_user.id} initiated contact with admin")


async def contact_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/contact command"""
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
        parse_mode='Markdown',
        reply_markup=back_to_main_keyboard()
    )
    
    context.user_data['awaiting_support_message'] = True
    logger.info(f"User {user.id} used /contact command")


async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming messages when user is in support mode
    This should be checked in your main message handler
    """
    # Check if user is in support mode
    if not context.user_data.get('awaiting_support_message'):
        return False  # Not handling this message
    
    user = update.effective_user
    message = update.message
    
    # Get user info
    with get_db() as session:
        db_user = crud.get_user_by_telegram_id(session, user.id)
        if db_user:
            user_display = f"{db_user.full_name} (ID: {db_user.user_id})"
        else:
            user_display = f"{user.first_name} {user.last_name or ''}"
    
    # Build admin message
    admin_header = f"""
📩 **رسالة من مستخدم / User Message**

👤 {user_display}
📱 Telegram: {user.id}
🔗 [Profile](tg://user?id={user.id})

━━━━━━━━━━━━━━━
"""
    
    try:
        # Forward based on message type
        if message.text:
            await context.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=admin_header + f"📝 **Message:**\n{message.text}",
                parse_mode='Markdown'
            )
        
        elif message.photo:
            photo = message.photo[-1]
            caption = message.caption or ""
            await context.bot.send_photo(
                chat_id=config.ADMIN_CHAT_ID,
                photo=photo.file_id,
                caption=admin_header + f"📷 **Photo:**\n{caption}",
                parse_mode='Markdown'
            )
        
        elif message.document:
            await context.bot.send_document(
                chat_id=config.ADMIN_CHAT_ID,
                document=message.document.file_id,
                caption=admin_header + "📄 **Document**",
                parse_mode='Markdown'
            )
        
        elif message.voice:
            await context.bot.send_voice(
                chat_id=config.ADMIN_CHAT_ID,
                voice=message.voice.file_id,
                caption=admin_header + "🎤 **Voice message**",
                parse_mode='Markdown'
            )
        
        else:
            # For other types, just forward
            await context.bot.forward_message(
                chat_id=config.ADMIN_CHAT_ID,
                from_chat_id=message.chat_id,
                message_id=message.message_id
            )
            await context.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=admin_header,
                parse_mode='Markdown'
            )
        
        # Confirm to user
        await message.reply_text(
            "✅ **تم إرسال رسالتك للإدارة**\n"
            "سيتم الرد عليك قريباً.\n\n"
            "✅ **Message sent successfully**\n"
            "You will receive a response soon.",
            parse_mode='Markdown',
            reply_markup=back_to_main_keyboard()
        )
        
        logger.info(f"✅ Support message forwarded from user {user.id}")
        
        # Clear flag
        context.user_data['awaiting_support_message'] = False
        return True  # Message was handled
        
    except Exception as e:
        logger.error(f"Error forwarding support message: {e}")
        await message.reply_text(
            "❌ حدث خطأ. يرجى المحاولة لاحقاً.\n"
            "❌ Error occurred. Please try again later.",
            reply_markup=back_to_main_keyboard()
        )
        context.user_data['awaiting_support_message'] = False
        return True
