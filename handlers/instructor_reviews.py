"""
Instructor review handlers
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from database import crud, get_db
from utils.keyboards import course_info_buttons_keyboard, review_instructor_keyboard
from utils.messages import instructor_reviews_message, course_description_details
import logging

logger = logging.getLogger(__name__)


async def show_instructor_reviews_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show instructor reviews for a course"""
    query = update.callback_query
    await query.answer()
    
    course_id = int(query.data.split('_')[-1])
    user_id = query.from_user.id
    
    with get_db() as session:
        course = crud.get_course_by_id(session, course_id)
        
        if not course:
            await query.edit_message_text("❌ الدورة غير موجودة")
            return
        
        # Get reviews and average rating
        reviews = crud.get_instructor_reviews(session, course_id)
        avg_rating = crud.get_instructor_average_rating(session, course_id)
        
        message = instructor_reviews_message(course, reviews, avg_rating)
        
        # Add "Rate Instructor" button
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [
            [InlineKeyboardButton("✍️ قيّم المدرب | Rate Instructor", callback_data=f"start_rate_{course_id}")],
            [InlineKeyboardButton("🔙 عودة | Back", callback_data=f"course_desc_{course_id}")]
        ]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


async def start_rate_instructor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start instructor rating process"""
    query = update.callback_query
    await query.answer()
    
    course_id = int(query.data.split('_')[-1])
    
    await query.edit_message_text(
        "⭐ **قيّم المدرب**\n\nاختر تقييمك من 1 إلى 5 نجوم:\n\n**Rate the Instructor**\n\nSelect your rating from 1 to 5 stars:",
        reply_markup=review_instructor_keyboard(course_id),
        parse_mode='Markdown'
    )


async def rate_instructor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle instructor rating selection"""
    query = update.callback_query
    await query.answer()
    
    # Parse: rate_instructor_{course_id}_{rating}
    parts = query.data.split('_')
    course_id = int(parts[2])
    rating = int(parts[3])
    
    telegram_user_id = query.from_user.id
    
    # Store rating in context and ask for review text
    context.user_data['pending_instructor_review'] = {
        'course_id': course_id,
        'rating': rating
    }
    
    await query.edit_message_text(
        f"✅ تقييمك: {'⭐' * rating}\n\nالآن، اكتب تعليقك عن المدرب (أو اضغط /skip للتخطي):\n\n**Your rating:** {'⭐' * rating}\n\nNow write your comment about the instructor (or /skip):"
    )


async def skip_review_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Skip review text and submit rating only"""
    if 'pending_instructor_review' not in context.user_data:
        await update.message.reply_text("لا يوجد تقييم معلق")
        return
    
    review_data = context.user_data.pop('pending_instructor_review')
    telegram_user_id = update.message.from_user.id
    
    with get_db() as session:
        internal_user = crud.get_user_by_telegram_id(session, telegram_user_id)
        
        if not internal_user:
            await update.message.reply_text("خطأ: المستخدم غير موجود")
            return
        
        # Save review without text
        crud.create_instructor_review(
            session,
            course_id=review_data['course_id'],
            user_id=internal_user.user_id,
            rating=review_data['rating'],
            review_text=None
        )
        
        await update.message.reply_text(
            f"✅ شكراً لتقييمك! ({'⭐' * review_data['rating']})\n\n✅ Thanks for your rating!"
        )


async def handle_review_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle review text input"""
    if 'pending_instructor_review' not in context.user_data:
        return  # Not in review process
    
    review_data = context.user_data.pop('pending_instructor_review')
    review_text = update.message.text
    telegram_user_id = update.message.from_user.id
    
    with get_db() as session:
        internal_user = crud.get_user_by_telegram_id(session, telegram_user_id)
        
        if not internal_user:
            await update.message.reply_text("خطأ: المستخدم غير موجود")
            return
        
        # Save review with text
        crud.create_instructor_review(
            session,
            course_id=review_data['course_id'],
            user_id=internal_user.user_id,
            rating=review_data['rating'],
            review_text=review_text
        )
        
        await update.message.reply_text(
            f"✅ شكراً لتقييمك ومراجعتك! ({'⭐' * review_data['rating']})\n\n✅ Thanks for your rating and review!"
        )
# ADD this function to your instructor_reviews.py

async def review_instructor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /review_instructor command - show list of instructors user can review"""
    telegram_user_id = update.message.from_user.id
    
    with get_db() as session:
        internal_user = crud.get_user_by_telegram_id(session, telegram_user_id)
        
        if not internal_user:
            await update.message.reply_text("❌ المستخدم غير مسجل")
            return
        
        # Get instructors user can review (from enrolled courses)
        instructors = crud.get_user_reviewable_instructors(session, internal_user.user_id)
        
        if not instructors:
            await update.message.reply_text(
                "لا يوجد مدربين يمكنك تقييمهم حالياً.\n"
                "سجّل في دورة أولاً!\n\n"
                "No instructors to review yet.\n"
                "Enroll in a course first!"
            )
            return
        
        message = "⭐ **اختر مدرباً لتقييمه:**\n**Choose an instructor to review:**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        
        keyboard = []
        for instructor in instructors:
            avg_rating = crud.get_instructor_average_rating(session, instructor.instructor_id)
            existing_review = crud.get_user_instructor_review(session, instructor.instructor_id, internal_user.user_id)
            
            rating_text = f" ({avg_rating}⭐)" if avg_rating else ""
            review_status = " ✅" if existing_review else ""
            
            message += f"👨‍🏫 **{instructor.name}**{rating_text}{review_status}\n"
            message += f"   📚 {instructor.specialization or 'غير محدد'}\n\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{'✏️ تعديل' if existing_review else '⭐ قيّم'} {instructor.name}",
                    callback_data=f"start_rate_{instructor.instructor_id}"
                )
            ])
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
