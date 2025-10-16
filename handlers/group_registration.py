"""
Group Registration - Link courses to Telegram groups
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import crud, get_db
from utils.helpers import is_admin_user
import logging

logger = logging.getLogger(__name__)


async def register_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register this group with a course (must be called in group)"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Check if admin
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    # Check if in a group
    if chat.type not in ['group', 'supergroup']:
        await update.message.reply_text(
            "❌ This command must be used in a Telegram group.\n\n"
            "**Steps:**\n"
            "1. Create a Telegram group\n"
            "2. Add this bot to the group as admin\n"
            "3. Use /register_group in the group",
            parse_mode='Markdown'
        )
        return
    
    # Check if bot is admin
    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if bot_member.status not in ['administrator', 'creator']:
            await update.message.reply_text(
                "❌ Bot must be an administrator in this group!\n\n"
                "**Required permissions:**\n"
                "• Invite users via link\n"
                "• Manage chat",
                parse_mode='Markdown'
            )
            return
    except Exception as e:
        logger.error(f"Error checking bot status: {e}")
        await update.message.reply_text("❌ Failed to check bot permissions.")
        return
    
    # Get courses without group
    with get_db() as session:
        courses = crud.get_all_courses(session)
        available_courses = [c for c in courses if not c.telegram_group_id]
        
        if not available_courses:
            await update.message.reply_text(
                "📭 No courses available for registration.\n\n"
                "All courses are already linked to groups."
            )
            return
        
        # Create keyboard with available courses
        keyboard = []
        for course in available_courses:
            keyboard.append([InlineKeyboardButton(
                f"{course.course_id} - {course.course_name}",
                callback_data=f"link_group_{course.course_id}"
            )])
        
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_link_group")])
        
        await update.message.reply_text(
            f"📚 **Link Group to Course**\n\n"
            f"**Group:** {chat.title}\n"
            f"**Group ID:** `{chat.id}`\n\n"
            f"Select the course to link with this group:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


async def link_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle group linking"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_link_group":
        await query.edit_message_text("❌ Group linking cancelled.")
        return
    
    course_id = int(query.data.split('_')[2])
    chat = query.message.chat
    
    with get_db() as session:
        course = crud.get_course_by_id(session, course_id)
        
        if not course:
            await query.edit_message_text("❌ Course not found.")
            return
        
        # Check if course already has a group
        if course.telegram_group_id:
            await query.edit_message_text(
                f"⚠️ Course **{course.course_name}** is already linked to another group.",
                parse_mode='Markdown'
            )
            return
        
        # Link group to course
        course.telegram_group_id = str(chat.id)
        
        # Generate invite link with join request (NO member_limit with creates_join_request)
        try:
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=chat.id,
                creates_join_request=True,  # Requires approval
                name=f"{course.course_name} - Verified Students"  # Optional: name the link
            )
            course.telegram_group_link = invite_link.invite_link
            session.commit()
            
            logger.info(f"✅ Course {course_id} ({course.course_name}) linked to group {chat.id} ({chat.title})")
            
            await query.edit_message_text(
                f"✅ **Group Linked Successfully!**\n\n"
                f"📚 **Course:** {course.course_name}\n"
                f"👥 **Group:** {chat.title}\n"
                f"🆔 **Group ID:** `{chat.id}`\n\n"
                f"🔗 **Invite Link:** `{invite_link.invite_link}`\n\n"
                f"**What happens next:**\n"
                f"• Students who complete payment for this course will receive the invite link\n"
                f"• When students click the link, they'll send a join request\n"
                f"• The bot will automatically approve verified students\n"
                f"• Non-registered users will be declined automatically",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Failed to create invite link: {e}")
            session.rollback()
            await query.edit_message_text(
                f"❌ **Failed to create invite link**\n\n"
                f"**Error:** {str(e)}\n\n"
                f"**Possible issues:**\n"
                f"• Bot doesn't have 'Invite users via link' permission\n"
                f"• Bot is not an admin in the group\n"
                f"• Group settings don't allow invite links\n\n"
                f"**Solution:**\n"
                f"1. Make sure bot is admin\n"
                f"2. Give bot 'Invite users via link' permission\n"
                f"3. Try again with /register_group",
                parse_mode='Markdown'
            )

