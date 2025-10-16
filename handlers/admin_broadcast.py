"""
Admin broadcast messaging system
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import crud, get_db
from database.models import PaymentStatus
from utils.helpers import is_admin_user
import logging

logger = logging.getLogger(__name__)

# Conversation states
(BROADCAST_TYPE, BROADCAST_MESSAGE, COURSE_SELECT, CONFIRM_BROADCAST) = range(4)


# ==================== /broadcast - Start broadcast flow ====================

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start broadcast message flow - Admin only"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("📢 All Students", callback_data="broadcast_all")],
        [InlineKeyboardButton("🎓 Specific Course", callback_data="broadcast_course")],
        [InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel")]
    ]
    
    await update.message.reply_text(
        "📢 **Broadcast Message**\n\n"
        "Who would you like to send this message to?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return BROADCAST_TYPE


async def broadcast_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast type selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "broadcast_cancel":
        await query.edit_message_text("❌ Broadcast cancelled.")
        return ConversationHandler.END
    
    elif query.data == "broadcast_all":
        context.user_data['broadcast_type'] = 'all'
        
        # Get count of students
        with get_db() as session:
            students = crud.get_all_active_students(session)
            count = len(students)
        
        await query.edit_message_text(
            f"📢 **Broadcast to All Students**\n\n"
            f"👥 Total Recipients: {count}\n\n"
            f"Please type your message now:\n\n"
            f"(Send /cancel to abort)"
        )
        
        return BROADCAST_MESSAGE
    
    elif query.data == "broadcast_course":
        context.user_data['broadcast_type'] = 'course'
        
        # Show course selection
        with get_db() as session:
            courses = crud.get_all_courses(session)
            
            if not courses:
                await query.edit_message_text("📭 No courses available.")
                return ConversationHandler.END
            
            keyboard = []
            for course in courses:
                student_count = crud.get_course_enrollment_count(session, course.course_id)
                keyboard.append([
                    InlineKeyboardButton(
                        f"{course.course_name} ({student_count} students)",
                        callback_data=f"bcast_course_{course.course_id}"
                    )
                ])
            keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel")])
            
            await query.edit_message_text(
                "🎓 **Select Course**\n\n"
                "Choose which course students to message:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return COURSE_SELECT


async def course_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle course selection for broadcast"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "broadcast_cancel":
        await query.edit_message_text("❌ Broadcast cancelled.")
        return ConversationHandler.END
    
    # Extract course_id from callback data
    course_id = int(query.data.split('_')[-1])
    context.user_data['broadcast_course_id'] = course_id
    
    with get_db() as session:
        course = crud.get_course_by_id(session, course_id)
        students = crud.get_course_students(session, course_id)
        
        if not students:
            await query.edit_message_text(
                f"📭 No students enrolled in **{course.course_name}** yet.",
                parse_mode='Markdown'
            )
            return ConversationHandler.END
        
        await query.edit_message_text(
            f"🎓 **Broadcast to {course.course_name}**\n\n"
            f"👥 Total Recipients: {len(students)}\n\n"
            f"Please type your message now:\n\n"
            f"(Send /cancel to abort)",
            parse_mode='Markdown'
        )
    
    return BROADCAST_MESSAGE


async def broadcast_message_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive broadcast message and show confirmation"""
    message_text = update.message.text.strip()
    
    if not message_text:
        await update.message.reply_text("❌ Message cannot be empty. Please try again or /cancel")
        return BROADCAST_MESSAGE
    
    context.user_data['broadcast_message'] = message_text
    
    broadcast_type = context.user_data.get('broadcast_type')
    
    # Show preview and confirmation
    if broadcast_type == 'all':
        with get_db() as session:
            students = crud.get_all_active_students(session)
            recipient_count = len(students)
        
        preview_text = (
            f"📢 **Broadcast Preview**\n\n"
            f"**Recipients:** All Students ({recipient_count} users)\n\n"
            f"**Message:**\n{message_text}\n\n"
            f"⚠️ This will send to {recipient_count} students. Confirm?"
        )
    
    else:  # course
        course_id = context.user_data.get('broadcast_course_id')
        with get_db() as session:
            course = crud.get_course_by_id(session, course_id)
            students = crud.get_course_students(session, course_id)
            recipient_count = len(students)
        
        preview_text = (
            f"🎓 **Broadcast Preview**\n\n"
            f"**Recipients:** {course.course_name} ({recipient_count} students)\n\n"
            f"**Message:**\n{message_text}\n\n"
            f"⚠️ Confirm sending to {recipient_count} students?"
        )
    
    keyboard = [
        [InlineKeyboardButton("✅ Send Now", callback_data="confirm_send")],
        [InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel")]
    ]
    
    await update.message.reply_text(
        preview_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return CONFIRM_BROADCAST


async def confirm_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and send broadcast message"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "broadcast_cancel":
        await query.edit_message_text("❌ Broadcast cancelled.")
        return ConversationHandler.END
    
    # Get broadcast details
    broadcast_type = context.user_data.get('broadcast_type')
    message_text = context.user_data.get('broadcast_message')
    
    await query.edit_message_text(
        "📤 Sending broadcast message...\n\nPlease wait..."
    )
    
    # Get recipients
    with get_db() as session:
        if broadcast_type == 'all':
            students = crud.get_all_active_students(session)
        else:
            course_id = context.user_data.get('broadcast_course_id')
            students = crud.get_course_students(session, course_id)
        
        # Check notification preferences
        recipients = []
        for student in students:
            prefs = crud.get_or_create_notification_preferences(session, student.user_id)
            if prefs.broadcast_messages:  # Only send if user allows broadcasts
                recipients.append(student)
    
    # Send messages
    success_count = 0
    failed_count = 0
    
    for student in recipients:
        try:
            # Format message with header
            formatted_message = f"📢 **Admin Announcement**\n\n{message_text}"
            
            await context.bot.send_message(
                chat_id=student.telegram_user_id,
                text=formatted_message,
                parse_mode='Markdown'
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to user {student.telegram_user_id}: {e}")
            failed_count += 1
    
    # Send result summary
    result_text = (
        f"✅ **Broadcast Complete!**\n\n"
        f"✅ Sent: {success_count}\n"
        f"❌ Failed: {failed_count}\n"
        f"📊 Total: {len(recipients)}\n\n"
    )
    
    if failed_count > 0:
        result_text += f"⚠️ Some messages failed (users may have blocked the bot)"
    
    await query.edit_message_text(result_text, parse_mode='Markdown')
    
    # Clear user data
    context.user_data.pop('broadcast_type', None)
    context.user_data.pop('broadcast_message', None)
    context.user_data.pop('broadcast_course_id', None)
    
    logger.info(f"Admin {query.from_user.id} sent broadcast to {success_count} students")
    
    return ConversationHandler.END


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel broadcast conversation"""
    await update.message.reply_text("❌ Broadcast cancelled.")
    
    context.user_data.pop('broadcast_type', None)
    context.user_data.pop('broadcast_message', None)
    context.user_data.pop('broadcast_course_id', None)
    
    return ConversationHandler.END
