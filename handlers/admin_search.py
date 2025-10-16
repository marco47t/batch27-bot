"""
Admin student search functionality
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import crud, get_db
from utils.helpers import is_admin_user
import logging

logger = logging.getLogger(__name__)

# Conversation state
SEARCH_INPUT = 0


async def search_student_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start student search - Admin only"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🔍 **Student Search**\n\n"
        "Enter student name or username to search:\n\n"
        "Examples:\n"
        "• `Ahmed`\n"
        "• `@john_doe`\n"
        "• `Mohamed Ali`\n\n"
        "Send /cancel to abort.",
        parse_mode='Markdown'
    )
    
    return SEARCH_INPUT


async def search_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search query and display results"""
    query = update.message.text.strip()
    
    if not query:
        await update.message.reply_text("❌ Search query cannot be empty. Try again or /cancel")
        return SEARCH_INPUT
    
    # Remove @ if username search
    if query.startswith('@'):
        query = query[1:]
    
    with get_db() as session:
        students = crud.search_students(session, query)
        
        if not students:
            await update.message.reply_text(
                f"📭 No students found matching: `{query}`\n\n"
                f"Try a different search term or /cancel",
                parse_mode='Markdown'
            )
            return SEARCH_INPUT
        
        # Display results
        result_text = f"🔍 **Search Results for:** `{query}`\n\n"
        result_text += f"📊 Found {len(students)} student(s):\n\n"
        
        for idx, student in enumerate(students, 1):
            # Get enrollment count
            enrollments = session.query(crud.Enrollment).filter(
                crud.Enrollment.user_id == student.user_id
            ).all()
            
            verified_count = sum(1 for e in enrollments if e.payment_status == crud.PaymentStatus.VERIFIED)
            pending_count = sum(1 for e in enrollments if e.payment_status == crud.PaymentStatus.PENDING)
            
            result_text += f"**{idx}. {student.first_name} {student.last_name or ''}**\n"
            result_text += f"   🆔 User ID: `{student.telegram_user_id}`\n"
            result_text += f"   👤 Username: @{student.username or 'N/A'}\n"
            result_text += f"   📚 Courses: {verified_count} verified, {pending_count} pending\n"
            result_text += f"   📅 Registered: {student.registration_date.strftime('%Y-%m-%d')}\n"
            result_text += f"   {'✅ Active' if student.is_active else '❌ Inactive'}\n"
            result_text += f"   {'👑 Admin' if student.is_admin else '👤 Student'}\n\n"
        
        # Send results
        await update.message.reply_text(result_text, parse_mode='Markdown')
        
        logger.info(f"Admin {update.effective_user.id} searched for: {query} - found {len(students)} results")
    
    return ConversationHandler.END


async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel search"""
    await update.message.reply_text("❌ Search cancelled.")
    return ConversationHandler.END
