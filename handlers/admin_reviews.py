"""
Admin review viewing system
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import crud, get_db
from database.models import CourseReview
from utils.helpers import is_admin_user
import logging

logger = logging.getLogger(__name__)

# Conversation state
COURSE_SELECT = 0


async def view_reviews_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all reviews - Admin only"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    with get_db() as session:
        reviews = session.query(CourseReview).order_by(CourseReview.created_at.desc()).all()
        
        if not reviews:
            await update.message.reply_text("📭 No reviews yet.")
            return
        
        # Show recent reviews (last 10)
        message = "⭐ **Recent Reviews** (Last 10)\n\n"
        
        for review in reviews[:10]:
            stars = "⭐" * review.rating
            message += f"**{review.course.course_name}**\n"
            message += f"{stars} ({review.rating}/5)\n"
            message += f"👤 By: {review.user.first_name} {review.user.last_name or ''}\n"
            
            if review.comment:
                comment = review.comment[:100] + "..." if len(review.comment) > 100 else review.comment
                message += f"💬 \"{comment}\"\n"
            
            message += f"📅 {review.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        
        message += f"📊 Total Reviews: {len(reviews)}\n"
        message += f"\nUse /coursereviews to see reviews by course"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
        logger.info(f"Admin {user.id} viewed all reviews")


async def course_reviews_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select course to view reviews - Admin only"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return ConversationHandler.END
    
    with get_db() as session:
        courses = crud.get_all_courses(session)
        
        if not courses:
            await update.message.reply_text("📭 No courses available.")
            return ConversationHandler.END
        
        # Build course selection keyboard
        keyboard = []
        for course in courses:
            review_count = crud.get_course_review_count(session, course.course_id)
            avg_rating = crud.get_course_average_rating(session, course.course_id)
            
            if review_count > 0:
                stars = "⭐" * round(avg_rating)
                keyboard.append([
                    InlineKeyboardButton(
                        f"{course.course_name} - {stars} ({review_count})",
                        callback_data=f"view_reviews_{course.course_id}"
                    )
                ])
        
        if not keyboard:
            await update.message.reply_text("📭 No courses have reviews yet.")
            return ConversationHandler.END
        
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="reviews_cancel")])
        
        await update.message.reply_text(
            "📚 **Select Course to View Reviews:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return COURSE_SELECT


async def course_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle course selection and display reviews"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "reviews_cancel":
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END
    
    course_id = int(query.data.split('_')[-1])
    
    with get_db() as session:
        course = crud.get_course_by_id(session, course_id)
        reviews = crud.get_course_reviews(session, course_id)
        avg_rating = crud.get_course_average_rating(session, course_id)
        
        if not reviews:
            await query.edit_message_text(
                f"📭 No reviews for **{course.course_name}** yet.",
                parse_mode='Markdown'
            )
            return ConversationHandler.END
        
        # Build detailed review message
        stars = "⭐" * round(avg_rating)
        message = f"📚 **{course.course_name}**\n\n"
        message += f"⭐ Average Rating: {avg_rating}/5 {stars}\n"
        message += f"📊 Total Reviews: {len(reviews)}\n\n"
        message += "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Rating distribution
        rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for review in reviews:
            rating_counts[review.rating] += 1
        
        message += "**Rating Distribution:**\n"
        for rating in range(5, 0, -1):
            count = rating_counts[rating]
            bar = "█" * count
            message += f"{rating}⭐ {bar} ({count})\n"
        
        message += "\n━━━━━━━━━━━━━━━━━━━━\n\n"
        message += "**Recent Reviews:**\n\n"
        
        # Show individual reviews
        for idx, review in enumerate(reviews[:5], 1):
            stars_review = "⭐" * review.rating
            message += f"**{idx}. {review.user.first_name} {review.user.last_name or ''}**\n"
            message += f"{stars_review} ({review.rating}/5)\n"
            
            if review.comment:
                message += f"💬 \"{review.comment}\"\n"
            
            message += f"📅 {review.created_at.strftime('%Y-%m-%d')}\n\n"
        
        if len(reviews) > 5:
            message += f"... and {len(reviews) - 5} more reviews\n"
        
        await query.edit_message_text(message, parse_mode='Markdown')
        
        logger.info(f"Admin viewed reviews for course {course_id}")
    
    return ConversationHandler.END


async def cancel_review_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel review viewing"""
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


async def export_reviews_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export all reviews to CSV - Admin only"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    await update.message.reply_text("📊 Generating reviews export...\n\nPlease wait...")
    
    try:
        with get_db() as session:
            reviews = session.query(CourseReview).order_by(CourseReview.created_at.desc()).all()
            
            if not reviews:
                await update.message.reply_text("📭 No reviews to export.")
                return
            
            # Create CSV
            import csv
            import io
            from datetime import datetime
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Headers
            writer.writerow([
                'Review ID', 'Course Name', 'Student Name', 'Username',
                'Rating', 'Comment', 'Date'
            ])
            
            # Data rows
            for review in reviews:
                writer.writerow([
                    review.review_id,
                    review.course.course_name,
                    f"{review.user.first_name} {review.user.last_name or ''}".strip(),
                    review.user.username or 'N/A',
                    review.rating,
                    review.comment or '',
                    review.created_at.strftime('%Y-%m-%d %H:%M')
                ])
            
            # Send file
            output.seek(0)
            filename = f"reviews_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            await update.message.reply_document(
                document=output.getvalue().encode('utf-8'),
                filename=filename,
                caption=f"⭐ **Course Reviews Export**\n\n"
                       f"✅ Total Reviews: {len(reviews)}\n"
                       f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                parse_mode='Markdown'
            )
            
            logger.info(f"Admin {user.id} exported {len(reviews)} reviews")
            
    except Exception as e:
        logger.error(f"Failed to export reviews: {e}")
        await update.message.reply_text(f"❌ Export failed: {str(e)}")
