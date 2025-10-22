from datetime import datetime
import json
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from utils.keyboards import payment_upload_keyboard, back_to_main_keyboard, failed_receipt_admin_keyboard
from utils.messages import payment_instructions_message, receipt_processing_message, payment_success_message, payment_failed_message, error_message
from utils.helpers import validate_receipt_file, log_user_action, send_admin_notification
from utils.s3_storage import upload_receipt_to_s3, download_receipt_from_s3
import config
from database import crud, get_db
from database.models import PaymentStatus, TransactionStatus
from services.gemini_service import validate_receipt_with_gemini_ai
from services.fraud_detector import calculate_consolidated_fraud_score
import logging
import tempfile
import os

logger = logging.getLogger(__name__)


async def proceed_to_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle proceed to payment button click"""
    query = update.callback_query
    await query.answer()
    telegram_user_id = query.from_user.id
    
    logger.info(f"User {telegram_user_id} proceeding to payment")
    
    cart_total = context.user_data.get("cart_total_for_payment")
    pending_enrollment_ids = context.user_data.get("pending_enrollment_ids_for_payment", [])
    
    if not cart_total or not pending_enrollment_ids:
        logger.error(f"User {telegram_user_id} payment data missing: cart_total={cart_total}, enrollments={pending_enrollment_ids}")
        await query.edit_message_text(error_message("payment_data_missing"), reply_markup=back_to_main_keyboard())
        return
    
    context.user_data["current_payment_total"] = cart_total
    context.user_data["current_payment_enrollment_ids"] = pending_enrollment_ids
    context.user_data["awaiting_receipt_upload"] = True
    
    logger.info(f"User {telegram_user_id} payment initiated: amount=${cart_total}, enrollments={pending_enrollment_ids}")
    
    await query.edit_message_text(
        payment_instructions_message(cart_total),
        reply_markup=payment_upload_keyboard(),
        parse_mode='Markdown'
    )


async def receipt_upload_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle receipt image/document uploads with comprehensive fraud detection and S3 storage"""
    
    if not context.user_data.get("awaiting_receipt_upload"):
        return
    
    user = update.effective_user
    file = None
    telegram_user_id = user.id
    
    logger.info(f"Receipt upload started for user {telegram_user_id}")
    
    # GET INTERNAL USER ID FIRST
    with get_db() as session:
        db_user = crud.get_or_create_user(
            session,
            telegram_user_id=telegram_user_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        session.flush()
        internal_user_id = db_user.user_id
    
    logger.info(f"User {telegram_user_id} has internal ID: {internal_user_id}")
    
    # Validate file type
    if update.message.document:
        file = update.message.document
    elif update.message.photo:
        file = update.message.photo[-1]
    else:
        logger.warning(f"User {telegram_user_id} sent invalid file type")
        await update.message.reply_text("❌ Please send a valid image or PDF receipt.", reply_markup=payment_upload_keyboard())
        return
    
    if not validate_receipt_file(file):
        logger.warning(f"User {telegram_user_id} receipt validation failed")
        await update.message.reply_text("❌ Please send a valid image or PDF receipt.", reply_markup=payment_upload_keyboard())
        return
    
    # Download file to temporary location first
    file_info = await file.get_file()
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
        temp_path = temp_file.name
    
    # Download to temp path
    await file_info.download_to_drive(temp_path)
    
    logger.info(f"Receipt downloaded to temp path for user {telegram_user_id}: {temp_path}")
    log_user_action(telegram_user_id, "receipt_uploaded", f"temp_path={temp_path}")

    # Notify user that processing started
    await update.message.reply_text(receipt_processing_message(), reply_markup=None)

    # Get expected amount
    expected_amount_for_gemini = context.user_data.get("reupload_amount") or context.user_data.get("current_payment_total")

    if expected_amount_for_gemini is None:
        logger.error(f"User {telegram_user_id} missing expected payment amount")
        await update.message.reply_text(error_message("payment_amount_missing"), reply_markup=back_to_main_keyboard())
        log_user_action(telegram_user_id, "receipt_upload_failed", "expected_amount_for_gemini missing")
        context.user_data["awaiting_receipt_upload"] = False
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return

    # ==================== STEP 1: GEMINI AI VALIDATION ====================
    logger.info(f"Starting Gemini validation for user {telegram_user_id}: expected_amount=${expected_amount_for_gemini}")

    gemini_result = await validate_receipt_with_gemini_ai(
        temp_path,
        expected_amount_for_gemini,
        config.EXPECTED_ACCOUNT_NUMBER
    )

    logger.info(f"Gemini validation result: is_valid={gemini_result.get('is_valid')}, amount={gemini_result.get('amount')}, tx_id={gemini_result.get('transaction_id')}")

    # ==================== STEP 2: ENHANCED FRAUD DETECTION ====================
    logger.info(f"Starting enhanced fraud detection for user {telegram_user_id}")

    # ===== CHECK FOR DUPLICATE TRANSACTION ID =====
    transaction_id = gemini_result.get("transaction_id")
    duplicate_check_result = {
        "transaction_id_duplicate": False,
        "is_duplicate": False,
        "similarity_score": 0
    }

    # Open session for duplicate checks
    with get_db() as dup_session:
        if transaction_id:
            is_duplicate_tx = crud.check_duplicate_transaction_id(dup_session, transaction_id)
            if is_duplicate_tx:
                duplicate_check_result["transaction_id_duplicate"] = True
                duplicate_check_result["duplicate_transaction_id"] = transaction_id
                logger.warning(f"⚠️ Duplicate transaction ID detected: {transaction_id}")
            else:
                logger.info(f"✅ Transaction ID is unique: {transaction_id}")
        else:
            logger.warning(f"⚠️ No transaction ID extracted from receipt")

    # ===== IMAGE FORENSICS ANALYSIS =====
    from services.image_forensics import analyze_image_metadata
    from services.ela_detector import perform_ela

    metadata_analysis = analyze_image_metadata(temp_path)
    ela_analysis = perform_ela(temp_path)

    image_forensics_result = {
        "is_forged": ela_analysis.get("is_suspicious", False) or metadata_analysis.get("risk_level") == "HIGH",
        "ela_score": ela_analysis.get("risk_score", 0) * 20,
        "metadata_risk": metadata_analysis.get("risk_level", "LOW"),
        "metadata_flags": metadata_analysis.get("suspicious_flags", []),
        "ela_reasons": ela_analysis.get("reasons", [])
    }
    logger.info(f"Image forensics: is_forged={image_forensics_result.get('is_forged')}, ela_score={image_forensics_result.get('ela_score', 0)}")

    # ✅ COLLECT ALL PREVIOUS RECEIPTS FROM ALL ENROLLMENTS (FOR DUPLICATE DETECTION)
    all_previous_receipt_paths = []

    with get_db() as dup_session:
        # Get all enrollments for this user to check their previous receipts
        current_payment_enrollment_ids = context.user_data.get("current_payment_enrollment_ids", [])
        resubmission_enrollment_id = context.user_data.get("resubmission_enrollment_id")
        
        enrollment_ids_to_check = current_payment_enrollment_ids if not resubmission_enrollment_id else [resubmission_enrollment_id]
        
        # Collect previous receipts
        for eid in enrollment_ids_to_check:
            enrollment = crud.get_enrollment_by_id(dup_session, eid)
            if enrollment:
                receipt_data = enrollment.receipt_image_path
                if receipt_data:
                    if isinstance(receipt_data, str):
                        try:
                            # Try to parse as JSON array
                            receipt_list = json.loads(receipt_data)
                            if isinstance(receipt_list, list):
                                # New format: array of receipt objects
                                all_previous_receipt_paths.extend([r['path'] for r in receipt_list if isinstance(r, dict) and 'path' in r])
                            else:
                                # Old format: single string
                                all_previous_receipt_paths.append(receipt_data)
                        except (json.JSONDecodeError, TypeError):
                            # Not JSON, plain string path
                            all_previous_receipt_paths.append(receipt_data)


    logger.info(f"Checking duplicate against {len(all_previous_receipt_paths)} previous receipts for user {telegram_user_id}")

    # Now check duplicates against ALL previous receipts
    all_previous_receipt_paths = []

    with get_db() as dup_session:
        current_payment_enrollment_ids = context.user_data.get("current_payment_enrollment_ids", [])
        resubmission_enrollment_id = context.user_data.get("resubmission_enrollment_id")
        
        enrollment_ids_to_check = current_payment_enrollment_ids if not resubmission_enrollment_id else [resubmission_enrollment_id]
        
        for eid in enrollment_ids_to_check:
            enrollment = crud.get_enrollment_by_id(dup_session, eid)
            if enrollment and enrollment.receipt_image_path:
                # Split comma-separated paths
                receipt_paths = enrollment.receipt_image_path.split(',')
                # Filter out empty strings and add to list
                all_previous_receipt_paths.extend([path.strip() for path in receipt_paths if path.strip()])

    logger.info(f"Checking duplicate against {len(all_previous_receipt_paths)} previous receipts for user {telegram_user_id}")

    from services.duplicate_detector import check_duplicate_submission
    duplicate_image_check = check_duplicate_submission(internal_user_id, temp_path, previous_receipt_paths=all_previous_receipt_paths)

    duplicate_check_result["is_duplicate"] = duplicate_image_check.get("is_duplicate", False)
    duplicate_check_result["similarity_score"] = duplicate_image_check.get("similarity_percentage", 0)

    if duplicate_check_result["is_duplicate"]:
        logger.warning(f"⚠️ DUPLICATE RECEIPT DETECTED! User {telegram_user_id} tried to reuse receipt")
        logger.warning(f"   Original owner: {duplicate_image_check.get('original_user_name')} (@{duplicate_image_check.get('original_user_username')})")
        logger.warning(f"   Similarity: {duplicate_check_result['similarity_score']:.1f}%")
        logger.warning(f"   Match type: {duplicate_image_check.get('match_type')}")
        
        # Add high fraud contribution for duplicates
        duplicate_check_result["fraud_contribution"] = 55
        logger.info(f"⚠️ Duplicate detected - adding 55 points to fraud score")
    else:
        duplicate_check_result["fraud_contribution"] = 0

    # ===== CALCULATE CONSOLIDATED FRAUD SCORE =====
    fraud_analysis = calculate_consolidated_fraud_score(
        gemini_result,
        image_forensics_result,
        duplicate_check_result
    )

    logger.info(f"🎯 Fraud Analysis - Score: {fraud_analysis['fraud_score']}/100, Risk: {fraud_analysis['risk_level']}, Action: {fraud_analysis['recommendation']}")
    logger.info(f"📋 Fraud indicators: {fraud_analysis['fraud_indicators']}")

    # ==================== STEP 3: UPLOAD TO S3 ====================
    try:
        resubmission_enrollment_id = context.user_data.get("resubmission_enrollment_id")
        if resubmission_enrollment_id:
            enrollment_id_for_s3 = resubmission_enrollment_id
        else:
            current_payment_enrollment_ids = context.user_data.get("current_payment_enrollment_ids", [])
            enrollment_id_for_s3 = current_payment_enrollment_ids[0] if current_payment_enrollment_ids else 0
        
        s3_url = upload_receipt_to_s3(temp_path, internal_user_id, enrollment_id_for_s3)
        file_path = s3_url
        logger.info(f"✅ Receipt uploaded to S3: {s3_url}")
        
    except Exception as e:
        logger.error(f"❌ S3 upload failed: {e}")
        file_path = temp_path
        logger.warning(f"Using local temp path as fallback: {temp_path}")
    
    # ==================== DECISION LOGIC ====================
    
    # Get enrollments to update
    verified_courses = []
    group_links = []
    enrollment_ids_str = ""
    
    with get_db() as session:
        resubmission_enrollment_id = context.user_data.get("resubmission_enrollment_id")
        enrollments_to_update = []
        
        if resubmission_enrollment_id:
            logger.info(f"Processing resubmission for user {telegram_user_id}, enrollment {resubmission_enrollment_id}")
            enrollment = crud.get_enrollment_by_id(session, resubmission_enrollment_id)
            if enrollment and enrollment.user_id == internal_user_id:
                enrollments_to_update.append(enrollment)
        else:
            logger.info(f"Processing initial payment for user {telegram_user_id}")
            current_payment_enrollment_ids = context.user_data.get("current_payment_enrollment_ids", [])
            for eid in current_payment_enrollment_ids:
                enrollment = crud.get_enrollment_by_id(session, eid)
                if enrollment and enrollment.user_id == internal_user_id:
                    enrollments_to_update.append(enrollment)
        
        if not enrollments_to_update:
            logger.error(f"No enrollments found for user {telegram_user_id}")
            await update.message.reply_text(error_message("enrollment_not_found"), reply_markup=back_to_main_keyboard())
            log_user_action(telegram_user_id, "receipt_upload_failed", "No enrollments to update/process")
            context.user_data["awaiting_receipt_upload"] = False
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return
        
        enrollment_ids_to_update = [e.enrollment_id for e in enrollments_to_update]
        enrollment_ids_str = ', '.join(map(str, enrollment_ids_to_update))
        # ===== STORE RECEIPT METADATA IN DATABASE =====
        logger.info(f"💾 Storing receipt metadata for enrollments: {enrollment_ids_str}")
        
        for enrollment_id in enrollment_ids_to_update:
            metadata_stored = crud.update_enrollment_receipt_metadata(
                session,
                enrollment_id=enrollment_id,
                transaction_id=gemini_result.get("transaction_id"),
                transfer_date=gemini_result.get("transfer_datetime"),
                sender_name=gemini_result.get("sender_name") or gemini_result.get("recipient_name")
            )
            if metadata_stored:
                logger.info(f"✅ Metadata stored for enrollment {enrollment_id}")
            else:
                logger.warning(f"⚠️ Failed to store metadata for enrollment {enrollment_id}")
        
        session.commit()
        logger.info(f"💾 Receipt metadata committed to database")
        # ==================== FRAUD ACTION: REJECT ====================
        if fraud_analysis["recommendation"] == "REJECT":
            logger.warning(f"Receipt REJECTED for user {telegram_user_id}: Fraud detected with score {fraud_analysis['fraud_score']}")
            
            # Update transaction as rejected with fraud data
            transaction = None
            for enrollment in enrollments_to_update:
                crud.update_enrollment_status(
                    session,
                    enrollment.enrollment_id,
                    PaymentStatus.FAILED,
                    receipt_path=file_path,
                    admin_notes=f"FRAUD DETECTED (Score: {fraud_analysis['fraud_score']}): " + "; ".join(fraud_analysis["fraud_indicators"][:2])
                )
                logger.info(f"Updated enrollment {enrollment.enrollment_id} status to FAILED (fraud)")
                
                if not transaction:
                    if resubmission_enrollment_id:
                        from database.models import Transaction
                        transaction = session.query(Transaction).filter(
                            Transaction.enrollment_id == resubmission_enrollment_id
                        ).order_by(Transaction.submitted_date.desc()).first()
                        
                        if transaction:
                            transaction = crud.update_transaction(
                                session,
                                transaction.transaction_id,
                                status=TransactionStatus.REJECTED,
                                extracted_account=gemini_result.get("account_number"),
                                extracted_amount=gemini_result.get("amount"),
                                failure_reason=f"FRAUD DETECTED: " + "; ".join(fraud_analysis["fraud_indicators"]),
                                gemini_response=str(fraud_analysis)
                            )
                    else:
                        transaction = crud.create_transaction(session, enrollment.enrollment_id, file_path)
                        transaction = crud.update_transaction(
                            session,
                            transaction.transaction_id,
                            status=TransactionStatus.REJECTED,
                            extracted_account=gemini_result.get("account_number"),
                            extracted_amount=gemini_result.get("amount"),
                            failure_reason=f"FRAUD DETECTED: " + "; ".join(fraud_analysis["fraud_indicators"]),
                            gemini_response=str(fraud_analysis)
                        )
            
            session.commit()
            
            # Build detailed rejection message for user
            rejection_msg = user_message = """
❌ **لم يتم قبول الإيصال**

عذراً، لم نتمكن من التحقق من الإيصال المرسل.

سيتم مراجعته من قبل الإدارة خلال 24-48 ساعة.

إذا كانت لديك أية استفسارات، يرجى التواصل مع الإدارة.

---
❌ **Receipt Not Accepted**

Sorry, we couldn't verify the submitted receipt.

It will be reviewed by administration within 24-48 hours.

If you have any questions, please contact administration.
"""

            
            await update.message.reply_text(rejection_msg, reply_markup=back_to_main_keyboard(), parse_mode='HTML')
            
            # Send detailed admin alert with fraud analysis
            course_names = []
            for enrollment in enrollments_to_update:
                if enrollment.course:
                    course_names.append(enrollment.course.course_name)
            course_names_str = ", ".join(course_names) if course_names else "N/A"
            
            admin_msg = f"""
🚨 <b>FRAUD ALERT - Receipt Auto-Rejected</b>

👤 <b>User Information:</b>
Name: {user.first_name} {user.last_name or ''}
Username: @{user.username or 'N/A'}
ID: <code>{telegram_user_id}</code>

🔴 <b>Fraud Score: {fraud_analysis['fraud_score']}/100</b>
⚠️ <b>Risk Level: {fraud_analysis['risk_level']}</b>

📊 <b>Fraud Indicators:</b>
"""
            for ind in fraud_analysis["fraud_indicators"]:
                admin_msg += f"- {ind}\n"
            
            # Add duplicate receipt info if detected
            if duplicate_check_result.get("is_duplicate"):
                admin_msg += f"\n🔄 <b>DUPLICATE RECEIPT DETECTED:</b>\n"
                admin_msg += f"- Original Owner: {duplicate_image_check.get('original_user_name')} (@{duplicate_image_check.get('original_user_username')})\n"
                admin_msg += f"- Original User ID: <code>{duplicate_image_check.get('original_telegram_id')}</code>\n"
                admin_msg += f"- Similarity: {duplicate_check_result['similarity_score']:.1f}%\n"
                admin_msg += f"- Match Type: {duplicate_image_check.get('match_type')}\n"
                admin_msg += f"- Risk Level: {duplicate_image_check.get('risk_level')}\n"

            
            # Add ELA visual analysis if available
            ela_data = fraud_analysis.get("ela_check", {})
            if ela_data.get("suspicious_regions"):
                admin_msg += f"\n🔍 Suspected Edited Areas:\n"
                for region in ela_data["suspicious_regions"][:3]:
                    admin_msg += f"- {region}\n"
            
            # Add Gemini tampering indicators if available
            gemini_tampering = fraud_analysis.get("ai_validation", {}).get("tampering_indicators", [])
            if gemini_tampering:
                admin_msg += f"\n🤖 AI Detected Issues:\n"
                for indicator in gemini_tampering[:3]:
                    admin_msg += f"- {indicator}\n"
            
            admin_msg += f"""
🔍 Checks Performed:
{fraud_analysis.get('checks_performed', ['Fraud checks completed'])}

📄 Extracted Data:
- Account: {gemini_result.get('account_number', 'N/A')}
- Amount: {(gemini_result.get('amount') or 0):.2f} {gemini_result.get('currency', 'SDG')}
- Date: {gemini_result.get('date', 'N/A')}
- Expected: {expected_amount_for_gemini:.2f} SDG

🎯 Authenticity Score: {gemini_result.get('authenticity_score', 0)}/100

📚 Courses: {course_names_str}
📝 Enrollment IDs: {enrollment_ids_str}
"""
            
            try:
                # If duplicate detected, send BOTH receipts to admin
                if duplicate_check_result.get("is_duplicate"):
                    # Download and send ORIGINAL receipt first
                    original_receipt_path = duplicate_image_check.get("original_receipt_path")
                    if original_receipt_path:
                        if original_receipt_path.startswith('https://'):
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as orig_temp:
                                orig_temp_path = orig_temp.name
                            download_receipt_from_s3(original_receipt_path, orig_temp_path)
                            original_photo = orig_temp_path
                        else:
                            original_photo = original_receipt_path
                        
                        # Send original receipt
                        with open(original_photo, "rb") as f_orig:
                            await context.bot.send_photo(
                                chat_id=config.ADMIN_CHAT_ID,
                                photo=f_orig,
                                caption=f"📸 <b>ORIGINAL RECEIPT (FIRST SUBMISSION)</b>\n\nFrom: {duplicate_image_check.get('original_user_name')}\nUsername: @{duplicate_image_check.get('original_user_username')}\nTelegram ID: <code>{duplicate_image_check.get('original_telegram_id')}</code>\n\n⬇️ See next photo for duplicate attempt",
                                parse_mode='HTML'
                            )
                        
                        # Clean up original temp file
                        if original_receipt_path.startswith('https://') and os.path.exists(original_photo):
                            os.remove(original_photo)
                
                # Download current (duplicate) receipt from S3 if needed
                if file_path.startswith('https://'):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as download_temp:
                        download_temp_path = download_temp.name
                    download_receipt_from_s3(file_path, download_temp_path)
                    photo_to_send = download_temp_path
                else:
                    photo_to_send = file_path
                
                # Send current receipt with fraud alert
                with open(photo_to_send, "rb") as f:
                    await context.bot.send_photo(
                        chat_id=config.ADMIN_CHAT_ID,
                        photo=f,
                        caption=admin_msg[:1024],
                        reply_markup=failed_receipt_admin_keyboard(enrollment_ids_str, telegram_user_id),
                        parse_mode='HTML'
                    )
                
                # Clean up downloaded temp file
                if file_path.startswith('https://') and os.path.exists(photo_to_send):
                    os.remove(photo_to_send)
                
                logger.info(f"Sent fraud alert to admin for user {telegram_user_id}")
            except Exception as e:
                logger.error(f"Failed to send admin fraud alert: {e}")
                await send_admin_notification(context, admin_msg[:4096])

            
            # Clean up context and temp file
            context.user_data["awaiting_receipt_upload"] = False
            context.user_data.pop("cart_total_for_payment", None)
            context.user_data.pop("pending_enrollment_ids_for_payment", None)
            context.user_data.pop("current_payment_enrollment_ids", None)
            context.user_data.pop("current_payment_total", None)
            context.user_data.pop("resubmission_enrollment_id", None)
            context.user_data.pop("reupload_amount", None)
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            return
        
        # ==================== FRAUD ACTION: MANUAL REVIEW ====================
        elif fraud_analysis["recommendation"] == "MANUAL_REVIEW":
            logger.warning(f"Receipt flagged for MANUAL REVIEW for user {telegram_user_id}: Score {fraud_analysis['fraud_score']}")
            
            # Update as pending review
            transaction = None
            for enrollment in enrollments_to_update:
                crud.update_enrollment_status(
                    session,
                    enrollment.enrollment_id,
                    PaymentStatus.PENDING,
                    receipt_path=file_path,
                    admin_notes=f"MANUAL REVIEW REQUIRED (Score: {fraud_analysis['fraud_score']}): " + "; ".join(fraud_analysis["fraud_indicators"][:2])
                )
                logger.info(f"Updated enrollment {enrollment.enrollment_id} status to PENDING (manual review)")
                
                if not transaction:
                    if resubmission_enrollment_id:
                        from database.models import Transaction
                        transaction = session.query(Transaction).filter(
                            Transaction.enrollment_id == resubmission_enrollment_id
                        ).order_by(Transaction.submitted_date.desc()).first()
                        
                        if transaction:
                            transaction = crud.update_transaction(
                                session,
                                transaction.transaction_id,
                                status=TransactionStatus.PENDING,
                                extracted_account=gemini_result.get("account_number"),
                                extracted_amount=gemini_result.get("amount"),
                                failure_reason=f"FLAGGED FOR REVIEW: " + "; ".join(fraud_analysis["fraud_indicators"]),
                                gemini_response=str(fraud_analysis)
                            )
                        else:
                            transaction = crud.create_transaction(session, enrollment.enrollment_id, file_path)
                            transaction = crud.update_transaction(
                                session,
                                transaction.transaction_id,
                                status=TransactionStatus.PENDING,
                                extracted_account=gemini_result.get("account_number"),
                                extracted_amount=gemini_result.get("amount"),
                                failure_reason=f"FLAGGED FOR REVIEW: " + "; ".join(fraud_analysis["fraud_indicators"]),
                                gemini_response=str(fraud_analysis)
                            )
                    else:
                        transaction = crud.create_transaction(session, enrollment.enrollment_id, file_path)
                        transaction = crud.update_transaction(
                            session,
                            transaction.transaction_id,
                            status=TransactionStatus.PENDING,
                            extracted_account=gemini_result.get("account_number"),
                            extracted_amount=gemini_result.get("amount"),
                            failure_reason=f"FLAGGED FOR REVIEW: " + "; ".join(fraud_analysis["fraud_indicators"]),
                            gemini_response=str(fraud_analysis)
                        )
            
            session.commit()
            
            # Notify user about manual review
            review_msg = f"""
        ⏳ **قيد المراجعة**
        تم استلام الإيصال وسيتم مراجعته من قبل الإدارة.
        ⏱️ سيتم الرد خلال 24-48 ساعة.
        شكراً لتفهمك.

        ---

        ⏳ **Under Review**
        Receipt received and will be reviewed by administration.
        ⏱️ You will receive a response within 24-48 hours.
        Thank you for your patience.
        """
            await update.message.reply_text(review_msg, reply_markup=back_to_main_keyboard(), parse_mode='HTML')
            
            # Send admin notification for manual review
            course_names = []
            for enrollment in enrollments_to_update:
                if enrollment.course:
                    course_names.append(enrollment.course.course_name)
            course_names_str = ", ".join(course_names) if course_names else "N/A"
            
            review_admin_msg = f"""
        ⚠️ <b>MANUAL REVIEW REQUIRED</b>

        👤 <b>User Information:</b>
        Name: {user.first_name} {user.last_name or ''}
        Username: @{user.username or 'N/A'}
        ID: <code>{telegram_user_id}</code>

        🟡 <b>Fraud Score: {fraud_analysis['fraud_score']}/100</b>
        ⚠️ <b>Risk Level: {fraud_analysis['risk_level']}</b>

        <b>⚠️ Warning Indicators:</b>
        """
            
            for ind in fraud_analysis["fraud_indicators"]:
                review_admin_msg += f"• {ind}\n"
            
            # ADD DUPLICATE DETECTION INFO
            if duplicate_check_result.get('is_duplicate'):
                review_admin_msg += f"\n<b>🚨 DUPLICATE RECEIPT DETECTED</b>\n"
                review_admin_msg += f"• <b>Original Owner:</b> {duplicate_image_check.get('original_user_name')} (@{duplicate_image_check.get('original_user_username')})\n"
                review_admin_msg += f"• <b>Original User ID:</b> <code>{duplicate_image_check.get('original_telegram_id')}</code>\n"
                review_admin_msg += f"• <b>Similarity:</b> {duplicate_check_result.get('similarity_score', 0):.1f}%\n"
                review_admin_msg += f"• <b>Match Type:</b> {duplicate_image_check.get('match_type')}\n"
                review_admin_msg += f"• <b>Risk Level:</b> {duplicate_image_check.get('risk_level')}\n"
            
            review_admin_msg += f"""
        📄 <b>Extracted Data:</b>
        • Account: {gemini_result.get('account_number', 'N/A')}
        • Amount: {(gemini_result.get('amount') or 0):.2f} {gemini_result.get('currency', 'SDG')}
        • Expected: {expected_amount_for_gemini:.2f} SDG

        📚 <b>Courses:</b> {course_names_str}
        📝 <b>Enrollment IDs:</b> {enrollment_ids_str}

        🔍 <b>Action Required:</b> Please review and approve/reject manually.
        """
            
            try:
                # If duplicate detected, send BOTH receipts
                if duplicate_check_result.get("is_duplicate"):
                    # Download and send ORIGINAL receipt first
                    original_receipt_path = duplicate_image_check.get("original_receipt_path")
                    if original_receipt_path:
                        if original_receipt_path.startswith('https://'):
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as orig_temp:
                                orig_temp_path = orig_temp.name
                            download_receipt_from_s3(original_receipt_path, orig_temp_path)
                            original_photo = orig_temp_path
                        else:
                            original_photo = original_receipt_path
                        
                        # Send original receipt
                        with open(original_photo, "rb") as f_orig:
                            await context.bot.send_photo(
                                chat_id=config.ADMIN_CHAT_ID,
                                photo=f_orig,
                                caption=f"📸 <b>ORIGINAL RECEIPT</b>\n\n👤 Original Owner: {duplicate_image_check.get('original_user_name')}\n🆔 User ID: <code>{duplicate_image_check.get('original_telegram_id')}</code>\n\n⬇️ See next photo for duplicate attempt",
                                parse_mode='HTML'
                            )
                        
                        # Clean up original temp file
                        if original_receipt_path.startswith('https://') and os.path.exists(original_photo):
                            os.remove(original_photo)
                
                # Download current (duplicate or normal) receipt from S3 if needed
                if file_path.startswith('https://'):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as download_temp:
                        download_temp_path = download_temp.name
                    download_receipt_from_s3(file_path, download_temp_path)
                    photo_to_send = download_temp_path
                else:
                    photo_to_send = file_path
                
                with open(photo_to_send, "rb") as f:
                    await context.bot.send_photo(
                        chat_id=config.ADMIN_CHAT_ID,
                        photo=f,
                        caption=review_admin_msg[:1024],
                        reply_markup=failed_receipt_admin_keyboard(enrollment_ids_str, telegram_user_id),
                        parse_mode='HTML'
                    )
                
                # Clean up downloaded temp file
                if file_path.startswith('https://') and os.path.exists(photo_to_send):
                    os.remove(photo_to_send)
                
                logger.info(f"Sent manual review request to admin for user {telegram_user_id}")
            except Exception as e:
                logger.error(f"Failed to send admin review request: {e}")
                await send_admin_notification(context, review_admin_msg[:4096])
            
            # Clean up context and temp file
            context.user_data["awaiting_receipt_upload"] = False
            context.user_data.pop("cart_total_for_payment", None)
            context.user_data.pop("pending_enrollment_ids_for_payment", None)
            context.user_data.pop("current_payment_enrollment_ids", None)
            context.user_data.pop("current_payment_total", None)
            context.user_data.pop("resubmission_enrollment_id", None)
            context.user_data.pop("reupload_amount", None)
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            return
        
        # ==================== FRAUD ACTION: APPROVE ====================
        # Low fraud score - proceed with normal validation
        result = gemini_result  # Use Gemini result for final validation
        extracted_amount = result.get("amount", 0)
        
        # ✅ CHECK FOR PARTIAL PAYMENT (amount is less but everything else is correct)
        # Allow 5 SDG tolerance
        if result["is_valid"] and extracted_amount < (expected_amount_for_gemini - 5):
            # PARTIAL PAYMENT DETECTED
            remaining_total = expected_amount_for_gemini - extracted_amount
            logger.info(f"⚠️ Partial payment detected for user {telegram_user_id}: paid {extracted_amount:.0f}, expected {expected_amount_for_gemini:.0f}, remaining {remaining_total:.0f}")
            
            # Get course names for notifications
            course_names = []
            for enrollment in enrollments_to_update:
                if enrollment.course:
                    course_names.append(enrollment.course.course_name)
            course_names_str = ", ".join(course_names) if course_names else "N/A"
            
            # ✅ CALCULATE REMAINING BALANCE FOR EACH ENROLLMENT
            enrollment_remaining_balances = []
            total_remaining_needed = 0
            
            for enrollment in enrollments_to_update:
                current_paid = enrollment.amount_paid or 0
                remaining_for_this = enrollment.payment_amount - current_paid
                enrollment_remaining_balances.append({
                    'enrollment': enrollment,
                    'remaining': remaining_for_this
                })
                total_remaining_needed += remaining_for_this
            
            logger.info(f"Total remaining needed across all enrollments: {total_remaining_needed:.0f} SDG")
            
            # ✅ DISTRIBUTE PAYMENT PROPORTIONALLY ACROSS ENROLLMENTS
            transaction = None
            remaining_to_distribute = extracted_amount
            
            for idx, item in enumerate(enrollment_remaining_balances):
                enrollment = item['enrollment']
                enrollment_remaining = item['remaining']
                
                # Calculate proportional amount
                if idx == len(enrollment_remaining_balances) - 1:
                    amount_for_this_enrollment = remaining_to_distribute
                else:
                    proportion = enrollment_remaining / total_remaining_needed
                    amount_for_this_enrollment = extracted_amount * proportion
                    remaining_to_distribute -= amount_for_this_enrollment
                
                # Apply payment
                current_paid = enrollment.amount_paid or 0
                enrollment.amount_paid = current_paid + amount_for_this_enrollment
                
                # Check if complete
                if enrollment.amount_paid >= enrollment.payment_amount:
                    enrollment.payment_status = PaymentStatus.VERIFIED
                    enrollment.verification_date = datetime.now()
                    logger.info(f"✅ Full payment reached for enrollment {enrollment.enrollment_id}")
                else:
                    enrollment.payment_status = PaymentStatus.PENDING
                    logger.info(f"⚠️ Still partial for enrollment {enrollment.enrollment_id}")
                
                existing_receipts = enrollment.receipt_image_path

                if existing_receipts:
                    # Append new receipt to existing ones
                    enrollment.receipt_image_path = existing_receipts + "," + file_path
                else:
                    # First receipt
                    enrollment.receipt_image_path = file_path
                
                session.flush()
                
                # Create/update transaction
                if not transaction:
                    if resubmission_enrollment_id:
                        from database.models import Transaction
                        transaction = session.query(Transaction).filter(
                            Transaction.enrollment_id == resubmission_enrollment_id
                        ).order_by(Transaction.submitted_date.desc()).first()
                        
                        if transaction:
                            transaction = crud.update_transaction(
                                session,
                                transaction.transaction_id,
                                status=TransactionStatus.PENDING,
                                extracted_account=result.get("account_number"),
                                extracted_amount=extracted_amount,
                                failure_reason=f"Partial payment: {extracted_amount:.0f}/{expected_amount_for_gemini:.0f} SDG. Remaining: {remaining_total:.0f} SDG",
                                gemini_response=result.get("raw_response", "") + f"\n\nFraud Score: {fraud_analysis['fraud_score']}"
                            )
                        else:
                            transaction = crud.create_transaction(session, enrollment.enrollment_id, file_path)
                            transaction = crud.update_transaction(
                                session,
                                transaction.transaction_id,
                                status=TransactionStatus.PENDING,
                                extracted_account=result.get("account_number"),
                                extracted_amount=extracted_amount,
                                failure_reason=f"Partial payment: {extracted_amount:.0f}/{expected_amount_for_gemini:.0f} SDG. Remaining: {remaining_total:.0f} SDG",
                                gemini_response=result.get("raw_response", "") + f"\n\nFraud Score: {fraud_analysis['fraud_score']}"
                            )
                    else:
                        transaction = crud.create_transaction(session, enrollment.enrollment_id, file_path)
                        transaction = crud.update_transaction(
                            session,
                            transaction.transaction_id,
                            status=TransactionStatus.PENDING,
                            extracted_account=result.get("account_number"),
                            extracted_amount=extracted_amount,
                            failure_reason=f"Partial payment: {extracted_amount:.0f}/{expected_amount_for_gemini:.0f} SDG. Remaining: {remaining_total:.0f} SDG",
                            gemini_response=result.get("raw_response", "") + f"\n\nFraud Score: {fraud_analysis['fraud_score']}"
                        )
            
            # ✅ COMMIT CHANGES BEFORE CHECKING
            session.commit()
            
            # ✅ NOW CHECK IF ALL ENROLLMENTS ARE VERIFIED
            all_verified = all(e.payment_status == PaymentStatus.VERIFIED for e in enrollments_to_update)
            
            if all_verified:
                # PAYMENT COMPLETE! Send group invites ONLY (no redundant success message)
                logger.info(f"✅ Payment completed for user {telegram_user_id}")
                
                from handlers.group_registration import send_course_invite_link
                
                # ✅ DELETE PROCESSING MESSAGE FIRST
                try:
                    if update.message:
                        await update.message.delete()
                except Exception as e:
                    logger.warning(f"Could not delete processing message: {e}")
                
                # Send group invites (this function sends its own message with the link)
                for e in enrollments_to_update:
                    if e.course:
                        await send_course_invite_link(update, context, telegram_user_id, e.course.course_id)
                
                # Clean up context
                context.user_data["awaiting_receipt_upload"] = False
                context.user_data.pop("cart_total_for_payment", None)
                context.user_data.pop("pending_enrollment_ids_for_payment", None)
                context.user_data.pop("current_payment_enrollment_ids", None)
                context.user_data.pop("current_payment_total", None)
                context.user_data.pop("resubmission_enrollment_id", None)
                context.user_data.pop("reupload_amount", None)
                
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                return  # Exit - payment complete!
            
            # ELSE: Still partial - send partial payment notification with breakdown
            partial_message = (
                f"⚠️ **المبلغ المدفوع ناقص**\n"
                f"💰 **المبلغ المدفوع:** {extracted_amount:.0f} SDG\n"
                f"✅ تم التحقق من الإيصال\n\n"
                f"📊 **توزيع الدفع:**\n"
            )
            
            # Show breakdown for each course
            for item in enrollment_remaining_balances:
                enrollment = item['enrollment']
                course_name = enrollment.course.course_name if enrollment.course else "Unknown"
                current_paid = enrollment.amount_paid or 0
                total_price = enrollment.payment_amount
                remaining = total_price - current_paid
                
                partial_message += f"• {course_name}: {current_paid:.0f}/{total_price:.0f} SDG"
                if remaining > 0:
                    partial_message += f" (متبقي: {remaining:.0f})\n"
                else:
                    partial_message += f" ✅ مكتمل\n"
            
            partial_message += (
                f"\n📊 **المبلغ المطلوب:** {expected_amount_for_gemini:.0f} SDG\n"
                f"⚠️ **المبلغ المتبقي:** {remaining_total:.0f} SDG\n\n"
                f"📝 **لإكمال الدفع:**\n"
                f"1️⃣ اذهب إلى **دوراتي** من القائمة الرئيسية\n"
                f"2️⃣ اختر الدورة\n"
                f"3️⃣ اضغط **إكمال الدفع** وأرسل إيصال المبلغ المتبقي\n\n"
                f"✅ سيتم تفعيل التسجيل بعد استلام المبلغ الكامل"
            )
            
            await update.message.reply_text(
                partial_message,
                reply_markup=back_to_main_keyboard(),
                parse_mode='Markdown'
            )
            
            # Send admin notification
            admin_partial_msg = f"""
        ⚠️ PARTIAL PAYMENT RECEIVED

        👤 User: {user.first_name} {user.last_name or ''}
        🆔 ID: {telegram_user_id}

        💰 Paid: {extracted_amount:.0f} SDG
        📊 Required: {expected_amount_for_gemini:.0f} SDG
        ⚠️ Remaining: {remaining:.0f} SDG

        📚 Courses: {course_names_str}
        📝 Enrollment IDs: {enrollment_ids_str}

        ✅ Account verified: {result.get('account_number')}
        🟢 Fraud score: {fraud_analysis['fraud_score']}/100

        ⏳ Waiting for remaining payment...
        """
            
            try:
                # Download from S3 if needed
                if file_path.startswith('https://'):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as download_temp:
                        download_temp_path = download_temp.name
                    download_receipt_from_s3(file_path, download_temp_path)
                    photo_to_send = download_temp_path
                else:
                    photo_to_send = file_path
                
                with open(photo_to_send, "rb") as f:
                    await context.bot.send_photo(
                        chat_id=config.ADMIN_CHAT_ID,
                        photo=f,
                        caption=admin_partial_msg[:1024],
                        parse_mode='HTML'
                    )
                
                if file_path.startswith('https://') and os.path.exists(photo_to_send):
                    os.remove(photo_to_send)
            except Exception as e:
                logger.error(f"Failed to send admin notification: {e}")
            
            # Clean up context
            context.user_data["awaiting_receipt_upload"] = False
            context.user_data.pop("cart_total_for_payment", None)
            context.user_data.pop("pending_enrollment_ids_for_payment", None)
            context.user_data.pop("current_payment_enrollment_ids", None)
            context.user_data.pop("current_payment_total", None)
            context.user_data.pop("resubmission_enrollment_id", None)
            context.user_data.pop("reupload_amount", None)
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            return  # ✅ STOP HERE for partial payment
        
        # ✅ CONTINUE WITH FULL PAYMENT (existing logic)
        transaction = None
        for enrollment in enrollments_to_update:
            payment_status = PaymentStatus.VERIFIED if result["is_valid"] else PaymentStatus.FAILED
            
            # ✅ If verified, set amount_paid to full amount
            if result["is_valid"]:
                enrollment.amount_paid = enrollment.payment_amount
            
            crud.update_enrollment_status(
                session,
                enrollment.enrollment_id,
                payment_status,
                receipt_path=file_path,
                admin_notes=result.get("reason") if not result["is_valid"] else f"Fraud score: {fraud_analysis['fraud_score']}"
            )
            
            logger.info(f"Updated enrollment {enrollment.enrollment_id} status to {payment_status}")
            
            if not transaction:
                if resubmission_enrollment_id:
                    from database.models import Transaction
                    transaction = session.query(Transaction).filter(
                        Transaction.enrollment_id == resubmission_enrollment_id
                    ).order_by(Transaction.submitted_date.desc()).first()
                    
                    if transaction:
                        transaction = crud.update_transaction(
                            session,
                            transaction.transaction_id,
                            status=TransactionStatus.APPROVED if result["is_valid"] else TransactionStatus.REJECTED,
                            extracted_account=result.get("account_number"),
                            extracted_amount=result.get("amount"),
                            failure_reason=result.get("reason", ""),
                            gemini_response=result.get("raw_response", "") + f"\n\nFraud Score: {fraud_analysis['fraud_score']}"
                        )
                        logger.info(f"Updated transaction {transaction.transaction_id}")
                    else:
                        transaction = crud.create_transaction(session, enrollment.enrollment_id, file_path)
                        transaction = crud.update_transaction(
                            session,
                            transaction.transaction_id,
                            status=TransactionStatus.APPROVED if result["is_valid"] else TransactionStatus.REJECTED,
                            extracted_account=result.get("account_number"),
                            extracted_amount=result.get("amount"),
                            failure_reason=result.get("reason", ""),
                            gemini_response=result.get("raw_response", "") + f"\n\nFraud Score: {fraud_analysis['fraud_score']}"
                        )
                        logger.info(f"Created new transaction {transaction.transaction_id}")
                else:
                    transaction = crud.create_transaction(session, enrollment.enrollment_id, file_path)
                    transaction = crud.update_transaction(
                        session,
                        transaction.transaction_id,
                        status=TransactionStatus.APPROVED if result["is_valid"] else TransactionStatus.REJECTED,
                        extracted_account=result.get("account_number"),
                        extracted_amount=result.get("amount"),
                        failure_reason=result.get("reason", ""),
                        gemini_response=result.get("raw_response", "") + f"\n\nFraud Score: {fraud_analysis['fraud_score']}"
                    )
                    logger.info(f"Created transaction {transaction.transaction_id}")
        
        if result["is_valid"]:
            course_data_list = []
            group_links_list = []
            
            # Import the group invitation function
            from handlers.group_registration import send_course_invite_link
            
            for e in enrollments_to_update:
                if e.payment_status == PaymentStatus.VERIFIED:
                    course = e.course
                    if course:
                        # Extract data immediately while in session
                        course_data_list.append({
                            'course_id': course.course_id,
                            'course_name': course.course_name
                        })
                        
                        # Send course group invite link (auto-fetches if missing)
                        await send_course_invite_link(update, context, telegram_user_id, course.course_id)
                        
                        # Also keep for backwards compatibility in success message
                        if course.telegram_group_link:
                            group_links_list.append(course.telegram_group_link)
            if not resubmission_enrollment_id:
                crud.clear_user_cart(session, internal_user_id)
                logger.info(f"Cleared cart for user {telegram_user_id}")
            
            session.commit()
    
    # ==================== USER NOTIFICATIONS ====================
    
    if result["is_valid"]:
        logger.info(f"Payment SUCCESS for user {telegram_user_id}, enrollments: {enrollment_ids_str}, Fraud Score: {fraud_analysis['fraud_score']}")
        
        # ✅ DELETE PROCESSING MESSAGE FIRST
        try:
            if update.message:
                await update.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete processing message: {e}")
        
        # ✅ NO redundant success message - send_course_invite_link already sent the success message with group link
        
        log_user_action(telegram_user_id, "payment_success", f"enrollment_ids={enrollment_ids_str}, fraud_score={fraud_analysis['fraud_score']}")
    else:
        logger.warning(f"Payment FAILED for user {telegram_user_id}: {result.get('reason')}, Fraud Score: {fraud_analysis['fraud_score']}")
        
        # Send user notification
        await update.message.reply_text(
            payment_failed_message(result.get("reason", "Invalid receipt.")),
            reply_markup=back_to_main_keyboard(),
            parse_mode='HTML'
        )
        
        # Send admin notification with receipt image
        extracted_account = result.get('account_number', 'N/A')
        extracted_amount = result.get('amount', 0)
        extracted_currency = result.get('currency', 'SDG')
        
        # Get course names for admin notification
        course_names = []
        with get_db() as temp_session:
            for eid in enrollment_ids_to_update:
                enrollment = crud.get_enrollment_by_id(temp_session, eid)
                if enrollment and enrollment.course:
                    course_names.append(enrollment.course.course_name)
        course_names_str = ", ".join(course_names) if course_names else "N/A"
        
        admin_caption = f"""
🔴 Receipt Validation Failed

👤 User: {user.first_name} {user.last_name or ''}
Username: @{user.username or 'N/A'}
ID: {telegram_user_id}

📄 Extracted Data:
• Account: {extracted_account}
• Amount: {gemini_result.get('amount') or 0:.2f} {gemini_result.get('currency', 'SDG')}
• Expected: {expected_amount_for_gemini:.2f} SDG

🟢 Fraud Score: {fraud_analysis['fraud_score']}/100 (LOW RISK)

❌ Validation Issue:
{result.get('reason', 'Validation failed')[:150]}...

📚 Courses: {course_names_str}
📝 Enrollment IDs: {enrollment_ids_str}

⚠️ Action Required: Manual review recommended
"""
        
        try:
            # Download from S3 if needed
            if file_path.startswith('https://'):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as download_temp:
                    download_temp_path = download_temp.name
                download_receipt_from_s3(file_path, download_temp_path)
                photo_to_send = download_temp_path
            else:
                photo_to_send = file_path
            
            with open(photo_to_send, "rb") as f:
                await context.bot.send_photo(
                    chat_id=config.ADMIN_CHAT_ID,
                    photo=f,
                    caption=admin_caption,
                    reply_markup=failed_receipt_admin_keyboard(enrollment_ids_str, telegram_user_id),
                    parse_mode='HTML'
                )
            
            # Clean up downloaded temp file
            if file_path.startswith('https://') and os.path.exists(photo_to_send):
                os.remove(photo_to_send)
            
            logger.info(f"Sent admin notification with image for user {telegram_user_id}")
        except Exception as e:
            logger.error(f"Failed to send admin notification for user {telegram_user_id}: {e}")
            await send_admin_notification(
                context,
                f"Receipt validation failed for user {telegram_user_id}. File: {file_path}"
            )
    
    # Clean up context data
    context.user_data["awaiting_receipt_upload"] = False
    context.user_data.pop("cart_total_for_payment", None)
    context.user_data.pop("pending_enrollment_ids_for_payment", None)
    context.user_data.pop("current_payment_enrollment_ids", None)
    context.user_data.pop("current_payment_total", None)
    context.user_data.pop("resubmission_enrollment_id", None)
    context.user_data.pop("reupload_amount", None)
    
    # Clean up temporary file
    try:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            logger.info(f"Cleaned up temp file: {temp_path}")
    except Exception as e:
        logger.warning(f"Failed to clean up temp file {temp_path}: {e}")
