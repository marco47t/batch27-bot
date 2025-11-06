"""
Support/Contact Admin System - Simplified
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import crud, get_db
from utils.keyboards import back_to_main_keyboard
import config
import logging

logger = logging.getLogger(__name__)


async def contact_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/contact command"""
    user = update.effective_user
    
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
    
    context.user_data['awaiting_support_message'] = True
    logger.info(f"User {user.id} used /contact command")


async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming messages when user is in support mode
    """
    if not context.user_data.get('awaiting_support_message'):
        return False
    
    user = update.effective_user
    message = update.message
    
    admin_header = f"""
📩 **رسالة جديدة من مستخدم**

👤 **من:** {user.full_name}
🆔 **ID:** `{user.id}`
🔗 [الذهاب للمستخدم](tg://user?id={user.id})
"""
    
    # Keyboard for admin to reply
    reply_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ الرد على المستخدم", callback_data=f"admin_reply_{user.id}")]
    ])
    
    try:
        # Forward the message to the admin chat
        await context.bot.forward_message(
            chat_id=config.ADMIN_CHAT_ID,
            from_chat_id=user.id,
            message_id=message.message_id
        )
        # Send the header with user info and the reply button
        await context.bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=admin_header,
            reply_markup=reply_keyboard,
            parse_mode='Markdown'
        )
        
        await message.reply_text(
            "✅ **تم إرسال رسالتك للإدارة بنجاح.**\n"
            "سيتم الرد عليك في أقرب وقت ممكن.",
            parse_mode='Markdown',
            reply_markup=back_to_main_keyboard()
        )
        
        logger.info(f"✅ Support message forwarded from user {user.id}")
        
    except Exception as e:
        logger.error(f"Error forwarding support message: {e}")
        await message.reply_text(
            "❌ حدث خطأ أثناء إرسال رسالتك. يرجى المحاولة مرة أخرى.",
            reply_markup=back_to_main_keyboard()
        )
    finally:
        # Clear the flag
        context.user_data['awaiting_support_message'] = False
        return True


async def start_admin_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the reply process when an admin clicks the 'Reply to User' button."""
    query = update.callback_query
    await query.answer()
    
    admin_user = query.from_user
    
    try:
        target_user_id = int(query.data.split('_')[-1])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ خطأ: لم يتم العثور على معرّف المستخدم.")
        return

    # Store admin and target user IDs in context for the next step
    context.user_data['admin_replying'] = True
    context.user_data['admin_user_id'] = admin_user.id
    context.user_data['target_user_id_for_reply'] = target_user_id

    await query.message.reply_text(
        f"📝 **الرد على المستخدم {target_user_id}**\n\n"
        "أرسل رسالتك الآن. سيتم إرسالها مباشرة إلى المستخدم.",
        parse_mode='Markdown'
    )


async def handle_admin_reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the admin's reply message and sends it to the user."""
    # Check if the admin is in reply mode
    if not context.user_data.get('admin_replying'):
        return

    admin_user_id = context.user_data.get('admin_user_id')
    
    # Ensure the message is from the admin who initiated the reply
    if update.effective_user.id != admin_user_id:
        return

    target_user_id = context.user_data.get('target_user_id_for_reply')
    admin_reply_message = update.message

    if not target_user_id:
        await admin_reply_message.reply_text("❌ خطأ: لم يتم العثور على المستخدم المستهدف.")
        return

    try:
        # Send the admin's message to the target user
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"📨 **رد من الإدارة:**\n\n{admin_reply_message.text}"
        )
        
        # Confirm to the admin that the message was sent
        await admin_reply_message.reply_text("✅ تم إرسال ردك بنجاح.")
        
        logger.info(f"Admin {admin_user_id} replied to user {target_user_id}")

    except Exception as e:
        logger.error(f"Failed to send admin reply to user {target_user_id}: {e}")
        await admin_reply_message.reply_text(f"❌ فشل إرسال الرد. السبب: {e}")
    finally:
        # Clear the reply mode flags
        context.user_data.pop('admin_replying', None)
        context.user_data.pop('admin_user_id', None)
        context.user_data.pop('target_user_id_for_reply', None)

