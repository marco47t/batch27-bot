"""
Admin receipt viewing and management handlers
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, ConversationHandler
from database import crud, get_db
from database.models import TransactionStatus
from utils.helpers import is_admin_user
from utils.s3_storage import download_receipt_from_s3
from datetime import datetime
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

# Conversation states
(RECEIPT_USER_ID, RECEIPT_DATE_INPUT, RECEIPT_DATE_RANGE_START,
 RECEIPT_DATE_RANGE_END, RECEIPT_COURSE_SELECT) = range(5)


async def send_receipt_photo(update: Update, receipt_path: str, caption: str):
    """
    Helper function to send receipt photo (handles both S3 URLs and local paths)
    """
    try:
        # Check if it's an S3 URL
        if receipt_path.startswith('https://') or receipt_path.startswith('http://'):
            # Download from S3 to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                temp_path = temp_file.name
            
            try:
                download_receipt_from_s3(receipt_path, temp_path)
                
                # Send the photo
                with open(temp_path, 'rb') as photo:
                    await update.message.reply_photo(photo=photo, caption=caption)
                
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
            except Exception as e:
                logger.error(f"Failed to download from S3: {e}")
                await update.message.reply_text(f"{caption}\n\n❌ Failed to load image from S3")
                # Clean up temp file if it exists
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        else:
            # Local file path
            if os.path.exists(receipt_path):
                with open(receipt_path, 'rb') as photo:
                    await update.message.reply_photo(photo=photo, caption=caption)
            else:
                await update.message.reply_text(f"{caption}\n\n❌ Receipt image not found")
                
    except Exception as e:
        logger.error(f"Failed to send receipt image: {e}")
        await update.message.reply_text(f"{caption}\n\n❌ Failed to send image")


# ==================== /getreceipt - Get user receipts ====================

async def get_receipt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get receipts for a specific user - Admin only"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📸 **Get User Receipts**\n\n"
        "Enter the Telegram User ID or username:\n\n"
        "Example:\n"
        "• `919340565` (User ID)\n"
        "• `@username` (Username)\n\n"
        "Send /cancel to abort.",
        parse_mode='Markdown'
    )
    
    return RECEIPT_USER_ID


async def receipt_user_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive user ID and show their receipts"""
    user_input = update.message.text.strip()
    
    with get_db() as session:
        # Try to parse as Telegram ID (numeric)
        if user_input.isdigit():
            telegram_user_id = int(user_input)
            user = crud.get_user_by_telegram_id(session, telegram_user_id)
        # Or search by username
        elif user_input.startswith('@'):
            username = user_input[1:]
            from database.models import User
            user = session.query(User).filter(User.username == username).first()
        else:
            await update.message.reply_text(
                "❌ Invalid format. Use:\n"
                "• Numeric ID: `919340565`\n"
                "• Username: `@username`",
                parse_mode='Markdown'
            )
            return RECEIPT_USER_ID
        
        if not user:
            await update.message.reply_text(
                "❌ User not found.\n\n"
                "Try again or send /cancel to abort."
            )
            return RECEIPT_USER_ID
        
        # Get all transactions for this user
        transactions = crud.get_user_transactions(session, user_id=user.user_id)
        
        if not transactions:
            await update.message.reply_text(
                f"📭 No receipts found for user:\n\n"
                f"👤 Name: {user.first_name} {user.last_name or ''}\n"
                f"🆔 ID: {user.telegram_user_id}\n"
                f"👤 Username: @{user.username or 'N/A'}"
            )
            return ConversationHandler.END
        
        # Send summary first
        await update.message.reply_text(
            f"📊 **Receipts for User:**\n\n"
            f"👤 Name: {user.first_name} {user.last_name or ''}\n"
            f"🆔 ID: {user.telegram_user_id}\n"
            f"👤 Username: @{user.username or 'N/A'}\n\n"
            f"📸 Total Receipts: {len(transactions)}\n\n"
            f"Sending receipts...",
            parse_mode='Markdown'
        )
        
        # Send each receipt with details
        for idx, transaction in enumerate(transactions, 1):
            enrollment = transaction.enrollment
            course = enrollment.course
            
            status_emoji = {
                TransactionStatus.PENDING: "⏳",
                TransactionStatus.APPROVED: "✅",
                TransactionStatus.REJECTED: "❌"
            }
            
            caption = (
                f"📸 Receipt {idx}/{len(transactions)}\n\n"
                f"🎓 Course: {course.course_name}\n"
                f"💰 Amount: {enrollment.payment_amount:.0f} SDG\n"
                f"{status_emoji.get(transaction.status, '❓')} Status: {transaction.status.value}\n"
                f"📅 Submitted: {transaction.submitted_date.strftime('%Y-%m-%d %H:%M')}\n"
                f"🆔 Transaction ID: {transaction.transaction_id}"
            )
            
            # Send receipt image
            if transaction.receipt_image_path:
                await send_receipt_photo(update, transaction.receipt_image_path, caption)
            else:
                await update.message.reply_text(f"{caption}\n\n❌ No receipt image")
    
    return ConversationHandler.END


# ==================== /receiptstoday - Get today's receipts ====================

async def receipts_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get all receipts submitted today - Admin only"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    import pytz
    sudan_tz = pytz.timezone('Africa/Khartoum')
    today = datetime.now(sudan_tz).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    
    with get_db() as session:
        transactions = crud.get_transactions_by_date(session, today)
        
        if not transactions:
            await update.message.reply_text(
                f"📭 No receipts submitted today ({today.strftime('%Y-%m-%d')})"
            )
            return
        
        await update.message.reply_text(
            f"📊 **Receipts Today: {today.strftime('%Y-%m-%d')}**\n\n"
            f"📸 Total Receipts: {len(transactions)}\n\n"
            f"Sending receipts...",
            parse_mode='Markdown'
        )
        
        # Send receipts
        for idx, transaction in enumerate(transactions, 1):
            enrollment = transaction.enrollment
            user_obj = enrollment.user
            course = enrollment.course
            
            status_emoji = {
                TransactionStatus.PENDING: "⏳",
                TransactionStatus.APPROVED: "✅",
                TransactionStatus.REJECTED: "❌"
            }
            
            caption = (
                f"📸 Receipt {idx}/{len(transactions)}\n\n"
                f"👤 User: {user_obj.first_name} {user_obj.last_name or ''}\n"
                f"🆔 User ID: {user_obj.telegram_user_id}\n"
                f"🎓 Course: {course.course_name}\n"
                f"💰 Amount: {enrollment.payment_amount:.0f} SDG\n"
                f"{status_emoji.get(transaction.status, '❓')} Status: {transaction.status.value}\n"
                f"📅 Submitted: {transaction.submitted_date.strftime('%Y-%m-%d %H:%M')}"
            )
            
            if transaction.receipt_image_path:
                await send_receipt_photo(update, transaction.receipt_image_path, caption)
            else:
                await update.message.reply_text(f"{caption}\n\n❌ No receipt image")


# ==================== /receiptsdate - Get receipts by date ====================

async def receipts_date_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get receipts for a specific date - Admin only"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📅 **Get Receipts by Date**\n\n"
        "Enter the date (YYYY-MM-DD):\n\n"
        "Example: `2025-10-13`\n\n"
        "Send /cancel to abort.",
        parse_mode='Markdown'
    )
    
    return RECEIPT_DATE_INPUT


async def receipt_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive date and show receipts"""
    date_text = update.message.text.strip()
    
    try:
        target_date = datetime.strptime(date_text, '%Y-%m-%d')
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid date format. Use YYYY-MM-DD\n\n"
            "Example: 2025-10-13\n\n"
            "Try again or send /cancel to abort."
        )
        return RECEIPT_DATE_INPUT
    
    with get_db() as session:
        transactions = crud.get_transactions_by_date(session, target_date)
        
        if not transactions:
            await update.message.reply_text(
                f"📭 No receipts found for {date_text}"
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            f"📊 **Receipts for {date_text}**\n\n"
            f"📸 Total Receipts: {len(transactions)}\n\n"
            f"Sending receipts...",
            parse_mode='Markdown'
        )
        
        # Send receipts (same logic as receipts_today)
        for idx, transaction in enumerate(transactions, 1):
            enrollment = transaction.enrollment
            user_obj = enrollment.user
            course = enrollment.course
            
            status_emoji = {
                TransactionStatus.PENDING: "⏳",
                TransactionStatus.APPROVED: "✅",
                TransactionStatus.REJECTED: "❌"
            }
            
            caption = (
                f"📸 Receipt {idx}/{len(transactions)}\n\n"
                f"👤 User: {user_obj.first_name} {user_obj.last_name or ''}\n"
                f"🆔 User ID: {user_obj.telegram_user_id}\n"
                f"🎓 Course: {course.course_name}\n"
                f"💰 Amount: {enrollment.payment_amount:.0f} SDG\n"
                f"{status_emoji.get(transaction.status, '❓')} Status: {transaction.status.value}\n"
                f"📅 Submitted: {transaction.submitted_date.strftime('%Y-%m-%d %H:%M')}"
            )
            
            if transaction.receipt_image_path:
                await send_receipt_photo(update, transaction.receipt_image_path, caption)
            else:
                await update.message.reply_text(f"{caption}\n\n❌ No receipt image")
    
    return ConversationHandler.END


# ==================== Cancel handler ====================

async def cancel_receipt_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel receipt search"""
    await update.message.reply_text("❌ Search cancelled.")
    return ConversationHandler.END
