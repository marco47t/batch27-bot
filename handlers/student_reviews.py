"""
Student course review system
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import crud, get_db
from database.models import PaymentStatus
import logging

logger = logging.getLogger(__name__)

# Conversation states
(REVIEW_COURSE_SELECT, REVIEW_RATING, REVIEW_COMMENT) = range(3)


async def rate_course_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start course rating flow"""
    user = update.effective_user
    
    with get_db() as session:
        # Get user's completed courses without reviews
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # Get verified enrollments
        enrollments = session.query(crud.Enrollment).filter(
            crud.Enrollment.user_id == db_user.user_id,
            crud.Enrollment.payment_status == PaymentStatus.VERIFIED
        ).all()
        
        # Filter out courses already reviewed
        from database.models import CourseReview
        reviewable_enrollments = []
        for enrollment in enrollments:
            existing_review = session.query(CourseReview).filter(
                CourseReview.enrollment_id == enrollment.enrollment_id
            ).first()
            if not existing_review:
                reviewable_enrollments.append(enrollment)
        
        if not reviewable_enrollments:
            await update.message.reply_text(
                "📭 You have no courses to review.\n\n"
                "You can only review courses you've completed and haven't reviewed yet."
            )
            return ConversationHandler.END
        
        # Show course selection
        keyboard = []
        for enrollment in reviewable_enrollments:
            course = enrollment.course
            keyboard.append([
                InlineKeyboardButton(
                    f"{course.course_name}",
                    callback_data=f"review_course_{enrollment.enrollment_id}"
                )
            ])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="review_cancel")])
        
        await update.message.reply_text(
            "⭐ **Rate a Course**\n\n"
            "Select a course to review:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return REVIEW_COURSE_SELECT


async def review_course_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle course selection for review"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "review_cancel":
        await query.edit_message_text("❌ Review cancelled.")
        return ConversationHandler.END
    
    # Extract enrollment_id
    enrollment_id = int(query.data.split('_')[-1])
    context.user_data['review_enrollment_id'] = enrollment_id
    
    # Get course name
    with get_db() as session:
        enrollment = crud.get_enrollment_by_id(session, enrollment_id)
        course = enrollment.course
        context.user_data['review_course_name'] = course.course_name
    
    # Show rating buttons
    keyboard = [
        [
            InlineKeyboardButton("⭐", callback_data="rating_1"),
            InlineKeyboardButton("⭐⭐", callback_data="rating_2"),
            InlineKeyboardButton("⭐⭐⭐", callback_data="rating_3"),
        ],
        [
            InlineKeyboardButton("⭐⭐⭐⭐", callback_data="rating_4"),
            InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="rating_5"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="review_cancel")]
    ]
    
    await query.edit_message_text(
        f"⭐ **Rate: {course.course_name}**\n\n"
        f"How would you rate this course?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return REVIEW_RATING


async def review_rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle rating selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "review_cancel":
        await query.edit_message_text("❌ Review cancelled.")
        return ConversationHandler.END
    
    # Extract rating
    rating = int(query.data.split('_')[-1])
    context.user_data['review_rating'] = rating
    
    course_name = context.user_data.get('review_course_name')
    
    # Ask for comment
    keyboard = [[InlineKeyboardButton("⏭️ Skip Comment", callback_data="skip_comment")]]
    
    await query.edit_message_text(
        f"⭐ **Rate: {course_name}**\n\n"
        f"Rating: {'⭐' * rating}\n\n"
        f"Would you like to add a comment?\n\n"
        f"Type your comment or click Skip:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return REVIEW_COMMENT


async def review_comment_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive review comment"""
    comment = update.message.text.strip()
    
    await save_review(update, context, comment)
    return ConversationHandler.END


async def skip_comment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Skip comment and save review"""
    query = update.callback_query
    await query.answer()
    
    await save_review(query, context, None)
    return ConversationHandler.END


async def save_review(update_or_query, context: ContextTypes.DEFAULT_TYPE, comment: str = None):
    """Save the review to database"""
    enrollment_id = context.user_data.get('review_enrollment_id')
    rating = context.user_data.get('review_rating')
    course_name = context.user_data.get('review_course_name')
    
    with get_db() as session:
        enrollment = crud.get_enrollment_by_id(session, enrollment_id)
        
        # Create review
        from database.models import CourseReview
        review = CourseReview(
            user_id=enrollment.user_id,
            course_id=enrollment.course_id,
            enrollment_id=enrollment_id,
            rating=rating,
            comment=comment
        )
        session.add(review)
        session.commit()
        
        success_text = (
            f"✅ **Review Submitted!**\n\n"
            f"🎓 Course: {course_name}\n"
            f"⭐ Rating: {'⭐' * rating}\n"
        )
        
        if comment:
            success_text += f"💬 Comment: {comment}\n"
        
        success_text += "\nThank you for your feedback! 🙏"
        
        if hasattr(update_or_query, 'edit_message_text'):
            await update_or_query.edit_message_text(success_text, parse_mode='Markdown')
        else:
            await update_or_query.message.reply_text(success_text, parse_mode='Markdown')
        
        logger.info(f"User {enrollment.user_id} reviewed course {enrollment.course_id} - {rating} stars")
    
    # Clear context
    context.user_data.pop('review_enrollment_id', None)
    context.user_data.pop('review_rating', None)
    context.user_data.pop('review_course_name', None)


async def cancel_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel review"""
    await update.message.reply_text("❌ Review cancelled.")
    
    context.user_data.pop('review_enrollment_id', None)
    context.user_data.pop('review_rating', None)
    context.user_data.pop('review_course_name', None)
    
    return ConversationHandler.END
