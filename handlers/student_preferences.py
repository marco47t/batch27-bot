"""
Student notification preferences management
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import crud, get_db
import logging

logger = logging.getLogger(__name__)

# Conversation state
PREFERENCE_SELECT = 0


async def preferences_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View/edit notification preferences"""
    user = update.effective_user
    
    with get_db() as session:
        # Get or create user
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # Get preferences
        prefs = crud.get_or_create_notification_preferences(session, db_user.user_id)
        
        # Build message
        message = "🔔 **Notification Preferences**\n\n"
        message += "Choose which notifications you want to receive:\n\n"
        
        message += f"{'✅' if prefs.course_start_reminder else '❌'} Course Start Reminders (24h before)\n"
        message += f"{'✅' if prefs.registration_closing_reminder else '❌'} Registration Closing Reminders (48h before)\n"
        message += f"{'✅' if prefs.payment_status_updates else '❌'} Payment Status Updates\n"
        message += f"{'✅' if prefs.new_course_announcements else '❌'} New Course Announcements\n"
        message += f"{'✅' if prefs.broadcast_messages else '❌'} Admin Broadcast Messages\n\n"
        
        message += "Tap a button below to toggle:"
        
        # Build keyboard
        keyboard = [
            [InlineKeyboardButton(
                f"{'✅' if prefs.course_start_reminder else '❌'} Course Start Reminders",
                callback_data="pref_course_start_reminder"
            )],
            [InlineKeyboardButton(
                f"{'✅' if prefs.registration_closing_reminder else '❌'} Registration Closing",
                callback_data="pref_registration_closing_reminder"
            )],
            [InlineKeyboardButton(
                f"{'✅' if prefs.payment_status_updates else '❌'} Payment Updates",
                callback_data="pref_payment_status_updates"
            )],
            [InlineKeyboardButton(
                f"{'✅' if prefs.new_course_announcements else '❌'} New Courses",
                callback_data="pref_new_course_announcements"
            )],
            [InlineKeyboardButton(
                f"{'✅' if prefs.broadcast_messages else '❌'} Admin Messages",
                callback_data="pref_broadcast_messages"
            )],
            [InlineKeyboardButton("✅ Done", callback_data="pref_done")]
        ]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return PREFERENCE_SELECT


async def preference_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle a preference on/off"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "pref_done":
        await query.edit_message_text(
            "✅ **Preferences Saved!**\n\n"
            "Your notification settings have been updated.\n"
            "You can change them anytime with /preferences",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Extract preference name from callback data
    pref_name = query.data.replace('pref_', '')
    user = query.from_user
    
    with get_db() as session:
        # Get user
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # Get preferences
        prefs = crud.get_or_create_notification_preferences(session, db_user.user_id)
        
        # Toggle the preference
        current_value = getattr(prefs, pref_name)
        new_value = not current_value
        crud.update_notification_preference(session, db_user.user_id, pref_name, new_value)
        session.commit()
        
        # Reload preferences
        prefs = crud.get_or_create_notification_preferences(session, db_user.user_id)
        
        # Update message
        message = "🔔 **Notification Preferences**\n\n"
        message += "Choose which notifications you want to receive:\n\n"
        
        message += f"{'✅' if prefs.course_start_reminder else '❌'} Course Start Reminders (24h before)\n"
        message += f"{'✅' if prefs.registration_closing_reminder else '❌'} Registration Closing Reminders (48h before)\n"
        message += f"{'✅' if prefs.payment_status_updates else '❌'} Payment Status Updates\n"
        message += f"{'✅' if prefs.new_course_announcements else '❌'} New Course Announcements\n"
        message += f"{'✅' if prefs.broadcast_messages else '❌'} Admin Broadcast Messages\n\n"
        
        message += "Tap a button below to toggle:"
        
        # Rebuild keyboard with updated states
        keyboard = [
            [InlineKeyboardButton(
                f"{'✅' if prefs.course_start_reminder else '❌'} Course Start Reminders",
                callback_data="pref_course_start_reminder"
            )],
            [InlineKeyboardButton(
                f"{'✅' if prefs.registration_closing_reminder else '❌'} Registration Closing",
                callback_data="pref_registration_closing_reminder"
            )],
            [InlineKeyboardButton(
                f"{'✅' if prefs.payment_status_updates else '❌'} Payment Updates",
                callback_data="pref_payment_status_updates"
            )],
            [InlineKeyboardButton(
                f"{'✅' if prefs.new_course_announcements else '❌'} New Courses",
                callback_data="pref_new_course_announcements"
            )],
            [InlineKeyboardButton(
                f"{'✅' if prefs.broadcast_messages else '❌'} Admin Messages",
                callback_data="pref_broadcast_messages"
            )],
            [InlineKeyboardButton("✅ Done", callback_data="pref_done")]
        ]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        logger.info(f"User {db_user.user_id} toggled {pref_name} to {new_value}")
        
        return PREFERENCE_SELECT


async def cancel_preferences(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel preferences editing"""
    await update.message.reply_text("❌ Preferences cancelled.")
    return ConversationHandler.END
