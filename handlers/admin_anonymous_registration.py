"""
Handler for admin-driven anonymous course registrations.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from database import crud, get_db
from database.models import PaymentStatus, TransactionStatus
from utils.helpers import is_admin_user, save_receipt_image
from datetime import datetime

# Logger
logger = logging.getLogger(__name__)

# Conversation states
SELECT_COURSE, SELECT_CERTIFICATE, UPLOAD_RECEIPT = range(3)

# Anonymous user ID for tracking these registrations
ANONYMOUS_TELEGRAM_USER_ID = -1  # Using a negative number to avoid conflicts

async def start_anonymous_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the anonymous registration process for admins."""
    user_id = update.effective_user.id
    if not is_admin_user(user_id):
        await update.message.reply_text("❌ This command is for admins only.")
        return ConversationHandler.END

    with get_db() as session:
        courses = crud.get_all_active_courses(session)

    if not courses:
        await update.message.reply_text("There are no active courses to register a payment for.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(course.course_name, callback_data=f"anon_reg_course_{course.course_id}")]
        for course in courses
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Please select the course for the anonymous registration:",
        reply_markup=reply_markup,
    )
    return SELECT_COURSE

async def select_course_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the course selection."""
    query = update.callback_query
    await query.answer()

    course_id = int(query.data.split("_")[-1])
    context.user_data["anon_reg_course_id"] = course_id

    with get_db() as session:
        course = crud.get_course_by_id(session, course_id)
        if not course or not course.certificate_available:
            # If certificate is not available, skip this step
            context.user_data["anon_reg_with_certificate"] = False
            await query.edit_message_text("Please upload the receipt image for this registration.")
            return UPLOAD_RECEIPT

    keyboard = [
        [InlineKeyboardButton("Yes (With Certificate)", callback_data="anon_reg_cert_yes")],
        [InlineKeyboardButton("No (Without Certificate)", callback_data="anon_reg_cert_no")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"Registering for: {course.course_name}\n\nShould this registration include a certificate?",
        reply_markup=reply_markup,
    )
    return SELECT_CERTIFICATE

async def select_certificate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the certificate selection."""
    query = update.callback_query
    await query.answer()

    with_certificate = "yes" in query.data
    context.user_data["anon_reg_with_certificate"] = with_certificate

    await query.edit_message_text("Great. Now, please upload the receipt image for this registration.")
    return UPLOAD_RECEIPT

from services.gemini_service import validate_receipt_with_gemini_ai
import config

async def receipt_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the receipt upload and finalizes the anonymous registration."""
    admin_user = update.effective_user
    course_id = context.user_data.get("anon_reg_course_id")
    with_certificate = context.user_data.get("anon_reg_with_certificate")

    if course_id is None or with_certificate is None:
        await update.message.reply_text("Error: Context is missing. Please start over with /anonregister.")
        return ConversationHandler.END

    try:
        with get_db() as session:
            # Get or create the anonymous user
            anonymous_user = crud.get_or_create_user(
                session,
                telegram_user_id=ANONYMOUS_TELEGRAM_USER_ID,
                username="anonymous_registration",
                first_name="Anonymous",
                last_name="Registration",
            )
            session.commit()

            course = crud.get_course_by_id(session, course_id)
            if not course:
                await update.message.reply_text("Error: Course not found.")
                return ConversationHandler.END

            payment_amount = course.price
            if with_certificate and course.certificate_available:
                payment_amount += course.certificate_price

            file_path = save_receipt_image(update.message, ANONYMOUS_TELEGRAM_USER_ID)
            if not file_path:
                await update.message.reply_text("Could not save the receipt image. Please try again.")
                return UPLOAD_RECEIPT

            enrollment = crud.create_enrollment(
                session,
                user_id=anonymous_user.user_id,
                course_id=course_id,
                payment_amount=payment_amount,
            )
            enrollment.with_certificate = with_certificate
            enrollment.payment_status = PaymentStatus.VERIFIED
            enrollment.verification_date = datetime.utcnow()
            enrollment.receipt_image_path = file_path
            enrollment.admin_notes = f"Anonymous registration by admin: {admin_user.id}"
            session.flush()

            transaction = crud.create_transaction(
                session,
                enrollment_id=enrollment.enrollment_id,
                receipt_image_path=file_path,
            )
            session.commit()

            # Process with Gemini
            await update.message.reply_text("Processing receipt with AI...")
            gemini_result = await validate_receipt_with_gemini_ai(
                image_path=file_path,
                expected_amount=payment_amount,
                expected_accounts=config.EXPECTED_ACCOUNTS,
                user_id=ANONYMOUS_TELEGRAM_USER_ID,
            )

            # Update transaction with Gemini data
            crud.update_transaction(
                session,
                transaction_id=transaction.transaction_id,
                status=TransactionStatus.APPROVED,
                extracted_account=gemini_result.get("account_number"),
                extracted_amount=gemini_result.get("amount"),
                gemini_response=gemini_result.get("raw_response"),
                receipt_transaction_id=gemini_result.get("transaction_id"),
                receipt_transfer_datetime=gemini_result.get("transfer_datetime"),
                receipt_sender_name=gemini_result.get("sender_name"),
                receipt_amount=gemini_result.get("amount"),
                admin_reviewed=admin_user.id,
            )
            session.commit()

            cert_text = "with" if with_certificate else "without"
            await update.message.reply_text(
                f"✅ Anonymous registration successful!\n\n"
                f"Course: {course.course_name}\n"
                f"Amount: {payment_amount:.0f} SDG ({cert_text} certificate)\n"
                f"Receipt data has been extracted and saved.\n"
                f"The course revenue has been updated."
            )

    except Exception as e:
        logger.error(f"Error during anonymous registration: {e}", exc_info=True)
        await update.message.reply_text("An error occurred. Please check the logs and try again.")
    finally:
        context.user_data.pop("anon_reg_course_id", None)
        context.user_data.pop("anon_reg_with_certificate", None)

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the conversation."""
    await update.message.reply_text("Anonymous registration cancelled.")
    # Clean up user_data
    context.user_data.pop("anon_reg_course_id", None)
    context.user_data.pop("anon_reg_with_certificate", None)
    return ConversationHandler.END
