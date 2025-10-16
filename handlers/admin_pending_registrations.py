"""
Admin handler for viewing pending registrations (enrollments waiting for payment)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import crud, get_db
from database.models import PaymentStatus, Enrollment, User, Course
from utils.helpers import is_admin_user
from utils.keyboards import back_to_main_keyboard
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def admin_pending_registrations_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show all pending registrations (enrollments with PENDING payment status)
    Admin command: /pending_registrations
    """
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text(
            "❌ Admin access only.", 
            reply_markup=back_to_main_keyboard()
        )
        return
    
    await update.message.reply_text("🔍 Fetching pending registrations...")
    
    with get_db() as session:
        # Query all PENDING enrollments with user and course info
        pending_enrollments = session.query(Enrollment).filter(
            Enrollment.payment_status == PaymentStatus.PENDING
        ).order_by(Enrollment.enrollment_date.desc()).all()
        
        if not pending_enrollments:
            await update.message.reply_text(
                "✅ No pending registrations found!\n\nAll enrollments have been processed.",
                reply_markup=back_to_main_keyboard()
            )
            return
        
        # Build the message
        message = f"📋 **Pending Registrations Report**\n"
        message += f"_Total: {len(pending_enrollments)} enrollment(s) waiting for payment_\n\n"
        message += "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Group by user for better readability
        user_enrollments = {}
        for enrollment in pending_enrollments:
            user_id = enrollment.user_id
            if user_id not in user_enrollments:
                user_enrollments[user_id] = []
            user_enrollments[user_id].append(enrollment)
        
        # Format each user's pending enrollments
        for idx, (user_id, enrollments) in enumerate(user_enrollments.items(), 1):
            first_enrollment = enrollments[0]
            user = first_enrollment.user
            
            # User info
            user_display = f"{user.first_name or ''} {user.last_name or ''}".strip()
            if user.username:
                user_display += f" (@{user.username})"
            if not user_display:
                user_display = f"User {user.telegram_user_id}"
            
            message += f"**{idx}. {user_display}**\n"
            message += f"   📱 Telegram ID: `{user.telegram_user_id}`\n"
            message += f"   🆔 User DB ID: `{user.user_id}`\n\n"
            
            # List all pending courses for this user
            total_amount = 0
            for enrollment in enrollments:
                course = enrollment.course
                amount = enrollment.payment_amount or 0
                total_amount += amount
                amount_paid = enrollment.amount_paid or 0
                remaining = amount - amount_paid
                
                # Enrollment details
                message += f"   📚 **{course.course_name}**\n"
                message += f"      • Enrollment ID: `{enrollment.enrollment_id}`\n"
                message += f"      • Price: ${amount:.2f}\n"
                message += f"      • Paid: ${amount_paid:.2f}\n"
                message += f"      • Remaining: ${remaining:.2f}\n"
                message += f"      • Date: {enrollment.enrollment_date.strftime('%Y-%m-%d %H:%M')}\n"
                message += f"      • Receipt: {'✅ Yes' if enrollment.receipt_image_path else '❌ No'}\n\n"
            
            message += f"   💰 **Total for this user: ${total_amount:.2f}**\n"
            message += "   ━━━━━━━━━━━━━━━\n\n"
        
        # Summary statistics
        total_pending_amount = sum(e.payment_amount or 0 for e in pending_enrollments)
        total_paid = sum(e.amount_paid or 0 for e in pending_enrollments)
        with_receipts = sum(1 for e in pending_enrollments if e.receipt_image_path)
        without_receipts = len(pending_enrollments) - with_receipts
        
        message += "\n📊 **Summary:**\n"
        message += f"• Total pending enrollments: **{len(pending_enrollments)}**\n"
        message += f"• Total users waiting: **{len(user_enrollments)}**\n"
        message += f"• With receipts uploaded: **{with_receipts}**\n"
        message += f"• Without receipts: **{without_receipts}**\n"
        message += f"• Total pending amount: **${total_pending_amount:.2f}**\n"
        message += f"• Total already paid: **${total_paid:.2f}**\n"
        message += f"• Total remaining: **${total_pending_amount - total_paid:.2f}**\n"
        
        # Create keyboard with action buttons
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh_pending_registrations")],
            [InlineKeyboardButton("📊 View Statistics", callback_data="admin_stats")],
            [InlineKeyboardButton("← Back to Admin Menu", callback_data="admin_menu_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Split message if too long (Telegram limit is 4096 characters)
        if len(message) > 4000:
            # Send in chunks
            parts = []
            current_part = ""
            for line in message.split("\n"):
                if len(current_part) + len(line) + 1 > 4000:
                    parts.append(current_part)
                    current_part = line + "\n"
                else:
                    current_part += line + "\n"
            if current_part:
                parts.append(current_part)
            
            # Send all parts except last without markup
            for part in parts[:-1]:
                await update.message.reply_text(part, parse_mode='Markdown')
            
            # Send last part with keyboard
            await update.message.reply_text(
                parts[-1],
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

async def admin_pending_registrations_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback handler for pending registrations button in admin menu
    """
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    if not is_admin_user(user.id):
        await query.edit_message_text(
            "❌ Admin access only.",
            reply_markup=back_to_main_keyboard()
        )
        return
    
    # Update the message to show loading
    await query.edit_message_text("🔍 Fetching pending registrations...")
    
    with get_db() as session:
        # Query all PENDING enrollments
        pending_enrollments = session.query(Enrollment).filter(
            Enrollment.payment_status == PaymentStatus.PENDING
        ).order_by(Enrollment.enrollment_date.desc()).all()
        
        if not pending_enrollments:
            await query.edit_message_text(
                "✅ No pending registrations found!\n\nAll enrollments have been processed.",
                reply_markup=back_to_main_keyboard()
            )
            return
        
        # Build the message (same as above but shorter for callback)
        message = f"📋 **Pending Registrations**\n"
        message += f"_Total: {len(pending_enrollments)} enrollments_\n\n"
        
        # Summary statistics
        total_pending_amount = sum(e.payment_amount or 0 for e in pending_enrollments)
        total_paid = sum(e.amount_paid or 0 for e in pending_enrollments)
        with_receipts = sum(1 for e in pending_enrollments if e.receipt_image_path)
        without_receipts = len(pending_enrollments) - with_receipts
        
        # Group by user
        user_enrollments = {}
        for enrollment in pending_enrollments:
            user_id = enrollment.user_id
            if user_id not in user_enrollments:
                user_enrollments[user_id] = []
            user_enrollments[user_id].append(enrollment)
        
        message += "📊 **Quick Summary:**\n"
        message += f"• Total users waiting: **{len(user_enrollments)}**\n"
        message += f"• With receipts: **{with_receipts}**\n"
        message += f"• Without receipts: **{without_receipts}**\n"
        message += f"• Total amount: **${total_pending_amount:.2f}**\n"
        message += f"• Remaining to pay: **${total_pending_amount - total_paid:.2f}**\n\n"
        message += "_Use /pending_registrations for detailed report_"
        
        # Create keyboard
        keyboard = [
            [InlineKeyboardButton("📋 Detailed Report", callback_data="admin_detailed_pending_registrations")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh_pending_registrations")],
            [InlineKeyboardButton("← Back", callback_data="admin_menu_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

async def admin_refresh_pending_registrations_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh the pending registrations view"""
    # Just call the main callback handler again
    await admin_pending_registrations_callback(update, context)
