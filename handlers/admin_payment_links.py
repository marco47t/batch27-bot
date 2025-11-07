"""
Admin handler for creating direct registration links for courses.
"""
import secrets
import asyncio
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import crud, get_db
from utils.helpers import is_admin_user
import logging

logger = logging.getLogger(__name__)

# Conversation states
SELECT_COURSE, SELECT_CERTIFICATE = range(2)

async def create_payment_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin command to start the payment link creation process."""
    user = update.effective_user
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ This command is for admins only.")
        return ConversationHandler.END

    with get_db() as session:
        courses = crud.get_all_active_courses(session)
    
    if not courses:
        await update.message.reply_text("There are no active courses to create a link for.")
        return ConversationHandler.END

    keyboard = []
    for course in courses:
        keyboard.append([InlineKeyboardButton(course.course_name, callback_data=f"plink_course_{course.course_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please select a course to create a registration link for:", reply_markup=reply_markup)
    
    return SELECT_COURSE

async def select_course_for_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Callback for when an admin selects a course."""
    query = update.callback_query
    await query.answer()
    
    course_id = int(query.data.split("_")[-1])
    context.user_data['plink_course_id'] = course_id
    
    keyboard = [
        [InlineKeyboardButton("Yes (Includes Certificate Fee)", callback_data=f"plink_cert_yes")],
        [InlineKeyboardButton("No (Course Fee Only)", callback_data=f"plink_cert_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("Should this link include the certificate fee?", reply_markup=reply_markup)
    
    return SELECT_CERTIFICATE

async def generate_payment_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Generates and stores a unique payment link for the selected course.
    Uses an asyncio.Lock per user to prevent race conditions from rapid clicks.
    """
    query = update.callback_query
    user_id = query.from_user.id

    # Get or create a lock for this specific user to prevent double-clicks.
    user_locks = context.bot_data.setdefault('user_locks', {})
    user_lock = user_locks.setdefault(user_id, asyncio.Lock())

    if user_lock.locked():
        await query.answer("Please wait, your previous request is still processing.", show_alert=True)
        return ConversationHandler.END

    async with user_lock:
        await query.answer()
        
        try:
            course_id = context.user_data.get('plink_course_id')
            if not course_id:
                await query.edit_message_text("Error: Course selection not found. Please start over.")
                return ConversationHandler.END

            with_certificate = "yes" in query.data
            token = secrets.token_urlsafe(16)
            
            with get_db() as session:
                course = crud.get_course_by_id(session, course_id)
                if not course:
                    await query.edit_message_text("Error: Course not found. It may have been deleted.")
                    return ConversationHandler.END
                
                course_name = course.course_name
                
                crud.create_payment_link(session, token, course_id, with_certificate)
                session.commit()

            # Slugify the course name for a readable URL
            slug = re.sub(r'[^a-zA-Z0-9-]+', '', course_name.lower().replace(' ', '-'))

            bot_username = context.bot.username
            payment_link = f"https://t.me/{bot_username}?start=reg_{slug}_{token}"
            
            cert_status = " (with certificate)" if with_certificate else " (without certificate)"
            
            await query.edit_message_text(
                f"✅ Link created for **{course_name}**{cert_status}:\n\n"
                f"This is a reusable, permanent registration link. Anyone with this link can register for the course.\n\n"
                f"`{payment_link}`",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error generating payment link for user {user_id}: {e}", exc_info=True)
            await query.edit_message_text("An error occurred while generating the link. Please try again.")
        finally:
            context.user_data.pop('plink_course_id', None)

    return ConversationHandler.END

async def cancel_link_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the link creation conversation."""
    await update.message.reply_text("Link creation cancelled.")
    context.user_data.pop('plink_course_id', None)
    return ConversationHandler.END
