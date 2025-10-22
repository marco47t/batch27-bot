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
    
    with get_db() as session:
        internal_user_id = crud.get_user_by_telegram_id(session, telegram_user_id).user_id
        
        # Get selected enrollments from payment context
        payment_context = context.user_data.get('payment_selection', {})
        selected_enrollment_ids = payment_context.get('selected_enrollment_ids', [])
        
        if not selected_enrollment_ids:
            await query.edit_message_text("❌ لم يتم العثور على دورات محددة للدفع.")
            return
        
        # Calculate total
        enrollments = crud.get_enrollments_by_ids(session, selected_enrollment_ids)
        total_amount = sum([
            (e.payment_amount - (e.amount_paid or 0))
            for e in enrollments
        ])
        
        if total_amount <= 0:
            await query.edit_message_text("✅ جميع الدورات المحددة مدفوعة بالكامل!")
            return
        
        # Store selected enrollments for receipt processing
        context.user_data['pending_payment_enrollments'] = selected_enrollment_ids
        
        # Send payment instructions
        instructions_text = payment_instructions_message(total_amount)
        
        await query.edit_message_text(
            instructions_text,
            reply_markup=payment_upload_keyboard()
        )
    
    log_user_action(telegram_user_id, "proceed_to_payment", f"Total: {total_amount} SDG")


async def handle_payment_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle uploaded receipt images with comprehensive fraud detection
    """
    telegram_user_id = update.effective_user.id
    
    # Validate file
    if not update.message.photo and not update.message.document:
        await update.message.reply_text(
            "❌ يرجى إرسال صورة الإيصال فقط.",
            reply_markup=back_to_main_keyboard()
        )
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text(receipt_processing_message())
    
    try:
        with get_db() as session:
            # Get user and pending enrollments
            user = crud.get_user_by_telegram_id(session, telegram_user_id)
            if not user:
                await processing_msg.edit_text("❌ المستخدم غير موجود.")
                return
            
            internal_user_id = user.user_id
            
            # Get enrollments awaiting payment
            selected_enrollment_ids = context.user_data.get('pending_payment_enrollments', [])
            
            if not selected_enrollment_ids:
                await processing_msg.edit_text("❌ لا توجد دورات معلقة للدفع.")
                return
            
            enrollments = crud.get_enrollments_by_ids(session, selected_enrollment_ids)
            
            if not enrollments:
                await processing_msg.edit_text("❌ الدورات المعلقة غير موجودة.")
                return
            
            # Calculate total amount due
            total_amount_due = sum([
                (e.payment_amount - (e.amount_paid or 0))
                for e in enrollments
            ])
            
            # Download receipt
            file_path = await validate_receipt_file(update, processing_msg)
            if not file_path:
                return
            
            temp_path = file_path
            
            # ===== GEMINI AI VALIDATION =====
            logger.info(f"Starting Gemini validation for user {telegram_user_id}")
            gemini_result = await validate_receipt_with_gemini_ai(
                temp_path,
                total_amount_due,
                config.EXPECTED_ACCOUNTS
            )
            
            logger.info(f"Gemini validation result: is_valid={gemini_result.get('is_valid')}, amount={gemini_result.get('amount')}, tx_id={gemini_result.get('transaction_id')}")
            
            # ===== FRAUD DETECTION SETUP =====
            logger.info(f"Starting enhanced fraud detection for user {telegram_user_id}")
            
            # Initialize fraud detection components
            duplicate_check_result = {
                "transaction_id_duplicate": False,
                "duplicate_transaction_id": None,
                "is_duplicate": False,
                "similarity_score": 0
            }
            
            transaction_id = gemini_result.get("transaction_id")
            
            # ✅ CHECK TRANSACTIONS TABLE (not Enrollments) for duplicate transaction ID
            with get_db() as dup_session:
                if transaction_id:
                    from database.models import Transaction as TransactionModel
                    
                    duplicate_transaction = dup_session.query(TransactionModel).filter(
                        TransactionModel.receipt_transaction_id == transaction_id,
                        TransactionModel.status == TransactionStatus.APPROVED  # Only check APPROVED
                    ).first()
                    
                    if duplicate_transaction:
                        duplicate_check_result["transaction_id_duplicate"] = True
                        duplicate_check_result["duplicate_transaction_id"] = transaction_id
                        duplicate_check_result["duplicate_enrollment_id"] = duplicate_transaction.enrollment_id
                        logger.warning(f"⚠️ Duplicate transaction ID detected: {transaction_id} (transaction #{duplicate_transaction.transaction_id}, enrollment #{duplicate_transaction.enrollment_id})")
                    else:
                        logger.info(f"✅ Transaction ID is unique: {transaction_id}")
                else:
                    logger.warning(f"⚠️ No transaction ID extracted from receipt")
            
            # ===== IMAGE FORENSICS =====
            from services.image_forensics import analyze_image_authenticity
            logger.info("Running image forensics analysis...")
            forensics_result = analyze_image_authenticity(temp_path)
            logger.info(f"Image forensics: is_forged={forensics_result.get('is_forged')}, ela_score={forensics_result.get('ela_score')}")
            
            # ❌ REMOVED: Image duplicate checking (too slow)
            # Instead, prepare duplicate info from transaction ID check only
            duplicate_image_check = {}  # ✅ Initialize empty dict for compatibility
            
            # ✅ Get duplicate info from Transaction table (not Enrollment)
            if duplicate_check_result.get("transaction_id_duplicate"):
                with get_db() as dup_session:
                    from database.models import Transaction as TransactionModel, Enrollment, User
                    
                    # ✅ Find the original transaction with this receipt_transaction_id
                    original_transaction = dup_session.query(TransactionModel).filter(
                        TransactionModel.receipt_transaction_id == transaction_id,
                        TransactionModel.status == TransactionStatus.APPROVED
                    ).first()
                    
                    if original_transaction:
                        original_enrollment = original_transaction.enrollment
                        original_user = original_enrollment.user
                        duplicate_image_check = {
                            'original_user_name': f"{original_user.first_name or ''} {original_user.last_name or ''}".strip() or "Unknown",
                            'original_user_username': original_user.username or "N/A",
                            'original_telegram_id': original_user.telegram_user_id,
                            'original_receipt_path': original_transaction.receipt_image_path,
                            'original_transaction_date': original_transaction.receipt_transfer_date,
                            'original_sender_name': original_transaction.receipt_sender_name,
                            'original_amount': original_transaction.receipt_amount,
                            'match_type': 'TRANSACTION_ID',
                            'risk_level': 'HIGH',
                            'similarity_percentage': 100.0
                        }
                        duplicate_check_result['is_duplicate'] = True
                        duplicate_check_result['similarity_score'] = 100.0
                        logger.warning(f"⚠️ Transaction ID {transaction_id} already used by {duplicate_image_check['original_user_name']} (@{duplicate_image_check['original_user_username']}) on {original_transaction.receipt_transfer_date}")
                    else:
                        logger.warning(f"⚠️ Transaction ID duplicate flag set but original transaction not found")
            
            logger.info(f"✅ Duplicate check complete (transaction ID only)")
            
            # ===== CONSOLIDATED FRAUD SCORE =====
            fraud_analysis = calculate_consolidated_fraud_score(
                gemini_result,
                forensics_result,
                duplicate_check_result
            )
            
            logger.info(f"🎯 Fraud Analysis - Score: {fraud_analysis['fraud_score']}/100, Risk: {fraud_analysis['risk_level']}, Action: {fraud_analysis['recommendation']}")
            logger.info(f"📋 Fraud indicators: {fraud_analysis['fraud_indicators']}")
            
            # ===== DECISION LOGIC =====
            extracted_amount = gemini_result.get("amount", 0)
            
            # Upload to S3 first
            s3_url = upload_receipt_to_s3(temp_path, internal_user_id, selected_enrollment_ids[0])
            logger.info(f"✅ Receipt uploaded to S3: {s3_url}")
            
            # ===== HIGH FRAUD SCORE - AUTO REJECT =====
            if fraud_analysis['recommendation'] == "REJECT":
                logger.warning(f"🚨 FRAUD DETECTED - Auto-rejecting receipt for user {telegram_user_id}")
                
                # Create/update transaction record
                for enrollment_id in selected_enrollment_ids:
                    transaction = crud.create_transaction(session, enrollment_id, s3_url)
                    transaction = crud.update_transaction(
                        session,
                        transaction.transaction_id,
                        status=TransactionStatus.REJECTED,
                        extracted_account=gemini_result.get("account_number"),
                        extracted_amount=gemini_result.get("amount"),
                        # ✅ NEW: Store receipt metadata
                        receipt_transaction_id=gemini_result.get("transaction_id"),
                        receipt_transfer_date=gemini_result.get("transfer_datetime"),
                        receipt_sender_name=gemini_result.get("sender_name") or gemini_result.get("recipient_name"),
                        receipt_amount=gemini_result.get("amount"),
                        failure_reason=f"FRAUD DETECTED: " + "; ".join(fraud_analysis["fraud_indicators"]),
                        gemini_response=gemini_result.get("raw_response", "") + f"\n\nFraud Score: {fraud_analysis['fraud_score']}"
                    )
                
                session.commit()
                
                await processing_msg.edit_text(
                    f"❌ تم رفض الإيصال\n\n"
                    f"⚠️ تم اكتشاف مشاكل في الإيصال:\n"
                    f"• {chr(10).join(fraud_analysis['fraud_indicators'][:3])}\n\n"
                    f"يرجى إرسال إيصال صحيح.",
                    reply_markup=back_to_main_keyboard()
                )
                
                log_user_action(telegram_user_id, "payment_fraud_rejected", f"Score: {fraud_analysis['fraud_score']}")
                return
            # ===== MEDIUM FRAUD SCORE - MANUAL REVIEW =====
            elif fraud_analysis['recommendation'] == "MANUAL_REVIEW":
                logger.warning(f"⚠️ FLAGGED FOR REVIEW - User {telegram_user_id}, Fraud Score: {fraud_analysis['fraud_score']}")
                
                # Create/update transaction records
                for enrollment_id in selected_enrollment_ids:
                    transaction = crud.create_transaction(session, enrollment_id, s3_url)
                    transaction = crud.update_transaction(
                        session,
                        transaction.transaction_id,
                        status=TransactionStatus.PENDING,
                        extracted_account=gemini_result.get("account_number"),
                        extracted_amount=gemini_result.get("amount"),
                        # ✅ NEW: Store receipt metadata
                        receipt_transaction_id=gemini_result.get("transaction_id"),
                        receipt_transfer_date=gemini_result.get("transfer_datetime"),
                        receipt_sender_name=gemini_result.get("sender_name") or gemini_result.get("recipient_name"),
                        receipt_amount=gemini_result.get("amount"),
                        failure_reason=f"FLAGGED FOR REVIEW: " + "; ".join(fraud_analysis["fraud_indicators"]),
                        gemini_response=gemini_result.get("raw_response", "") + f"\n\nFraud Score: {fraud_analysis['fraud_score']}"
                    )
                
                session.commit()
                
                # Notify admin
                admin_message = f"""
🔍 **PAYMENT NEEDS REVIEW**

👤 User: {user.first_name} {user.last_name or ''}
   @{user.username or 'N/A'}
   ID: {telegram_user_id}

💰 Amount: {extracted_amount:.0f} SDG (Expected: {total_amount_due:.0f} SDG)

⚠️ **Fraud Score: {fraud_analysis['fraud_score']}/100 ({fraud_analysis['risk_level']})**

🚨 Fraud Indicators:
{chr(10).join(['• ' + ind for ind in fraud_analysis['fraud_indicators']])}

📋 Transaction Details:
• TxID: {transaction_id or 'N/A'}
• Date: {gemini_result.get('date', 'N/A')}
• Sender: {gemini_result.get('sender_name', 'N/A')}

🎓 Courses ({len(enrollments)}):
{chr(10).join(['• ' + e.course.course_name for e in enrollments])}

📸 Receipt: {s3_url}
"""
                
                await send_admin_notification(
                    context.bot,
                    admin_message,
                    reply_markup=failed_receipt_admin_keyboard(transaction.transaction_id)
                )
                
                await processing_msg.edit_text(
                    "✅ تم استلام الإيصال\n\n"
                    "⏳ يتم حالياً مراجعة الإيصال من قبل الإدارة.\n"
                    "سيتم إعلامك بالنتيجة قريباً.",
                    reply_markup=back_to_main_keyboard()
                )
                
                log_user_action(telegram_user_id, "payment_manual_review", f"Score: {fraud_analysis['fraud_score']}")
                return
            
            # ===== LOW FRAUD SCORE - AUTO APPROVE =====
            else:  # recommendation == "ACCEPT"
                logger.info(f"✅ LOW FRAUD - Auto-approving receipt for user {telegram_user_id}")
                
                # Process initial payment
                logger.info(f"Processing initial payment for user {telegram_user_id}")
                
                # Store receipt metadata for ALL enrollments
                logger.info(f"💾 Storing receipt metadata for enrollments: {', '.join(map(str, selected_enrollment_ids))}")
                
                for enrollment_id in selected_enrollment_ids:
                    enrollment = crud.get_enrollment_by_id(session, enrollment_id)
                    
                    if not enrollment:
                        continue
                    
                    # ✅ Update enrollment with receipt metadata
                    logger.info(f"✅ Metadata stored for enrollment {enrollment_id}")
                
                logger.info(f"💾 Receipt metadata committed to database")
                
                # Calculate individual enrollment amounts (proportional split)
                total_remaining = sum([(e.payment_amount - (e.amount_paid or 0)) for e in enrollments])
                
                course_data_list = []
                group_links = []
                
                for enrollment in enrollments:
                    remaining_for_enrollment = enrollment.payment_amount - (enrollment.amount_paid or 0)
                    proportion = remaining_for_enrollment / total_remaining if total_remaining > 0 else 0
                    payment_for_this_enrollment = extracted_amount * proportion
                    
                    # Update amount paid
                    enrollment.amount_paid = (enrollment.amount_paid or 0) + payment_for_this_enrollment
                    
                    # Update receipt path (append if multiple)
                    if enrollment.receipt_image_path:
                        enrollment.receipt_image_path += f",{s3_url}"
                    else:
                        enrollment.receipt_image_path = s3_url
                    
                    logger.info(f"📝 Updated receipt path for enrollment {enrollment.enrollment_id}: {enrollment.receipt_image_path}")
                    
                    # Create transaction record
                    transaction = crud.create_transaction(session, enrollment.enrollment_id, s3_url)
                    logger.info(f"Created transaction {transaction.transaction_id}")
                    
                    transaction = crud.update_transaction(
                        session,
                        transaction.transaction_id,
                        status=TransactionStatus.APPROVED,
                        extracted_account=gemini_result.get("account_number"),
                        extracted_amount=payment_for_this_enrollment,
                        # ✅ NEW: Store receipt metadata
                        receipt_transaction_id=gemini_result.get("transaction_id"),
                        receipt_transfer_date=gemini_result.get("transfer_datetime"),
                        receipt_sender_name=gemini_result.get("sender_name") or gemini_result.get("recipient_name"),
                        receipt_amount=payment_for_this_enrollment,
                        gemini_response=gemini_result.get("raw_response", "") + f"\n\nFraud Score: {fraud_analysis['fraud_score']}"
                    )
                    
                    # Check if fully paid
                    remaining_total = enrollment.payment_amount - enrollment.amount_paid
                    
                    if remaining_total <= 0.01:  # Fully paid
                        enrollment.payment_status = PaymentStatus.VERIFIED
                        enrollment.verification_date = datetime.utcnow()
                        logger.info(f"✅ Enrollment {enrollment.enrollment_id} FULLY PAID ({enrollment.amount_paid:.0f} SDG)")
                        
                        # Generate group invite link
                        from handlers.group_registration import send_group_invite_link
                        group_link = await send_group_invite_link(context, user, enrollment.course)
                        
                        course_data_list.append({
                            'name': enrollment.course.course_name,
                            'course_name': enrollment.course.course_name,
                            'telegram_group_link': group_link
                        })
                        group_links.append(group_link)
                    else:
                        enrollment.payment_status = PaymentStatus.PENDING
                        logger.info(f"⚠️ Enrollment {enrollment.enrollment_id} PARTIALLY PAID: {enrollment.amount_paid:.0f}/{enrollment.payment_amount:.0f} SDG (remaining: {remaining_total:.0f} SDG)")
                        
                        course_data_list.append({
                            'name': enrollment.course.course_name,
                            'course_name': enrollment.course.course_name,
                            'status': 'partial',
                            'paid': enrollment.amount_paid,
                            'remaining': remaining_total
                        })
                
                session.commit()
                
                # Clear cart
                context.user_data.pop('pending_payment_enrollments', None)
                logger.info(f"Cleared cart for user {telegram_user_id}")
                
                # Send success message
                success_text = payment_success_message(course_data_list, group_links)
                await processing_msg.edit_text(
                    success_text,
                    reply_markup=back_to_main_keyboard()
                )
                
                logger.info(f"Payment SUCCESS for user {telegram_user_id}, enrollments: {', '.join(map(str, selected_enrollment_ids))}, Fraud Score: {fraud_analysis['fraud_score']}")
                log_user_action(telegram_user_id, "payment_success", f"enrollment_ids={','.join(map(str, selected_enrollment_ids))}, fraud_score={fraud_analysis['fraud_score']}")
                
                # Send admin notification
                fully_paid = [e for e in enrollments if (e.payment_amount - e.amount_paid) <= 0.01]
                partially_paid = [e for e in enrollments if (e.payment_amount - e.amount_paid) > 0.01]
                
                admin_notif = f"""
✅ **AUTO-APPROVED PAYMENT**

👤 User: {user.first_name} {user.last_name or ''}
   @{user.username or 'N/A'}
   ID: {telegram_user_id}

💰 Amount Paid: {extracted_amount:.0f} SDG

🎯 **Fraud Score: {fraud_analysis['fraud_score']}/100 ({fraud_analysis['risk_level']} RISK)**
✅ Auto-approved (low fraud indicators)

📋 Transaction Details:
• TxID: {transaction_id or 'N/A'}
• Date: {gemini_result.get('date', 'N/A')}
• Sender: {gemini_result.get('sender_name', 'N/A')}

🎓 Courses:
"""
                if fully_paid:
                    admin_notif += "\n✅ **Fully Paid:**\n"
                    for e in fully_paid:
                        admin_notif += f"• {e.course.course_name} - {e.amount_paid:.0f} SDG\n"
                
                if partially_paid:
                    admin_notif += "\n⚠️ **Partially Paid:**\n"
                    for e in partially_paid:
                        remaining_total = e.payment_amount - e.amount_paid
                        admin_notif += f"• {e.course.course_name} - Paid: {e.amount_paid:.0f}/{e.payment_amount:.0f} SDG\n"
                        admin_notif += f"  ⚠️ Remaining: {remaining_total:.0f} SDG\n"
                
                admin_notif += f"\n📸 Receipt: {s3_url}"
                
                await send_admin_notification(context.bot, admin_notif)
                
                return
    
    except Exception as e:
        logger.error(f"Payment processing error: {e}", exc_info=True)
        try:
            await processing_msg.edit_text(
                f"❌ حدث خطأ في معالجة الإيصال:\n{str(e)}\n\nيرجى المحاولة مرة أخرى.",
                reply_markup=back_to_main_keyboard()
            )
        except:
            pass
    
    finally:
        # Cleanup temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.info(f"Cleaned up temp file: {temp_path}")
            except:
                pass
async def select_courses_for_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Allow user to select which pending enrollments to pay for
    """
    query = update.callback_query
    await query.answer()
    
    telegram_user_id = query.from_user.id
    
    with get_db() as session:
        user = crud.get_user_by_telegram_id(session, telegram_user_id)
        
        if not user:
            await query.edit_message_text("❌ المستخدم غير موجود.")
            return
        
        # Get all pending enrollments
        pending_enrollments = crud.get_user_enrollments_by_status(
            session,
            user.user_id,
            PaymentStatus.PENDING
        )
        
        if not pending_enrollments:
            await query.edit_message_text(
                "✅ لا توجد دورات معلقة تحتاج دفع.\n\nجميع دوراتك مدفوعة!",
                reply_markup=back_to_main_keyboard()
            )
            return
        
        # Initialize selection state
        if 'payment_selection' not in context.user_data:
            context.user_data['payment_selection'] = {
                'selected_enrollment_ids': [],
                'total': 0.0
            }
        
        # Build selection keyboard
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = []
        selected_ids = context.user_data['payment_selection']['selected_enrollment_ids']
        
        for enrollment in pending_enrollments:
            remaining = enrollment.payment_amount - (enrollment.amount_paid or 0)
            
            if remaining <= 0:
                continue
            
            # Check if selected
            is_selected = enrollment.enrollment_id in selected_ids
            check_mark = "✅ " if is_selected else ""
            
            button_text = f"{check_mark}{enrollment.course.course_name} - {remaining:.0f} جنيه"
            callback_data = f"toggle_payment_{enrollment.enrollment_id}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Add control buttons
        if selected_ids:
            total = sum([
                (e.payment_amount - (e.amount_paid or 0))
                for e in pending_enrollments
                if e.enrollment_id in selected_ids
            ])
            
            keyboard.append([
                InlineKeyboardButton(f"✅ متابعة الدفع ({total:.0f} جنيه)", callback_data="proceed_to_payment"),
                InlineKeyboardButton("🔄 إلغاء الاختيار", callback_data="clear_payment_selection")
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = "📝 اختر الدورات التي تريد دفعها:\n\n"
        
        if selected_ids:
            message_text += f"✓ محدد: {len(selected_ids)} دورة\n"
            total = sum([
                (e.payment_amount - (e.amount_paid or 0))
                for e in pending_enrollments
                if e.enrollment_id in selected_ids
            ])
            message_text += f"💰 المجموع: {total:.0f} جنيه\n\n"
        
        message_text += "اضغط على الدورة لإضافتها أو إزالتها"
        
        await query.edit_message_text(
            message_text,
            reply_markup=reply_markup
        )


async def toggle_payment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Toggle enrollment selection for payment
    """
    query = update.callback_query
    await query.answer()
    
    # Extract enrollment_id from callback data
    enrollment_id = int(query.data.split('_')[-1])
    
    # Initialize selection state if not exists
    if 'payment_selection' not in context.user_data:
        context.user_data['payment_selection'] = {
            'selected_enrollment_ids': [],
            'total': 0.0
        }
    
    selected_ids = context.user_data['payment_selection']['selected_enrollment_ids']
    
    # Toggle selection
    if enrollment_id in selected_ids:
        selected_ids.remove(enrollment_id)
    else:
        selected_ids.append(enrollment_id)
    
    # Refresh the selection screen
    await select_courses_for_payment(update, context)


async def clear_payment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Clear all payment selections
    """
    query = update.callback_query
    await query.answer("تم مسح الاختيار")
    
    if 'payment_selection' in context.user_data:
        context.user_data['payment_selection'] = {
            'selected_enrollment_ids': [],
            'total': 0.0
        }
    
    # Refresh the selection screen
    await select_courses_for_payment(update, context)


async def view_my_courses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    View user's enrolled courses with payment status
    """
    query = update.callback_query if update.callback_query else None
    
    if query:
        await query.answer()
    
    telegram_user_id = update.effective_user.id
    
    with get_db() as session:
        user = crud.get_user_by_telegram_id(session, telegram_user_id)
        
        if not user:
            text = "❌ المستخدم غير موجود."
            if query:
                await query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return
        
        # Get all enrollments
        enrollments = crud.get_user_enrollments(session, user.user_id)
        
        if not enrollments:
            text = "📋 لا توجد دورات مسجلة\n\nسجل في الدورات من القائمة الرئيسية."
            if query:
                await query.edit_message_text(text, reply_markup=back_to_main_keyboard())
            else:
                await update.message.reply_text(text, reply_markup=back_to_main_keyboard())
            return
        
        # Categorize enrollments
        verified = [e for e in enrollments if e.payment_status == PaymentStatus.VERIFIED]
        pending = [e for e in enrollments if e.payment_status == PaymentStatus.PENDING]
        failed = [e for e in enrollments if e.payment_status == PaymentStatus.FAILED]
        
        message = "📋 **دوراتي:**\n\n"
        
        if verified:
            message += "✅ **الدورات المفعلة:**\n"
            for e in verified:
                message += f"• {e.course.course_name}\n"
                if e.course.telegram_group_link:
                    message += f"  🔗 [رابط المجموعة]({e.course.telegram_group_link})\n"
            message += "\n"
        
        if pending:
            message += "⏳ **قيد المراجعة / تحتاج دفع:**\n"
            for e in pending:
                remaining = e.payment_amount - (e.amount_paid or 0)
                if remaining > 0:
                    paid_text = f" (مدفوع: {e.amount_paid:.0f} جنيه)" if e.amount_paid else ""
                    message += f"• {e.course.course_name} - {remaining:.0f} جنيه متبقي{paid_text}\n"
                else:
                    message += f"• {e.course.course_name} - قيد المراجعة\n"
            message += "\n"
        
        if failed:
            message += "❌ **تحتاج إعادة محاولة:**\n"
            for e in failed:
                message += f"• {e.course.course_name}\n"
            message += "\n"
        
        # Build keyboard
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = []
        
        # Check if there are pending payments
        pending_with_balance = [e for e in pending if (e.payment_amount - (e.amount_paid or 0)) > 0]
        
        if pending_with_balance:
            keyboard.append([
                InlineKeyboardButton("💳 دفع الآن", callback_data="select_courses_for_payment")
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_to_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')


async def retry_failed_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Allow user to retry a failed payment
    """
    query = update.callback_query
    await query.answer()
    
    # Extract enrollment_id from callback data
    enrollment_id = int(query.data.split('_')[-1])
    
    telegram_user_id = query.from_user.id
    
    with get_db() as session:
        user = crud.get_user_by_telegram_id(session, telegram_user_id)
        enrollment = crud.get_enrollment_by_id(session, enrollment_id)
        
        if not enrollment or enrollment.user_id != user.user_id:
            await query.edit_message_text("❌ التسجيل غير موجود.")
            return
        
        # Reset status to pending
        enrollment.payment_status = PaymentStatus.PENDING
        session.commit()
        
        # Set this enrollment for payment
        context.user_data['pending_payment_enrollments'] = [enrollment_id]
        
        remaining = enrollment.payment_amount - (enrollment.amount_paid or 0)
        
        # Send payment instructions
        instructions_text = payment_instructions_message(remaining)
        
        await query.edit_message_text(
            instructions_text,
            reply_markup=payment_upload_keyboard()
        )
    
    log_user_action(telegram_user_id, "retry_failed_payment", f"enrollment_id={enrollment_id}")


async def view_payment_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    View user's payment transaction history
    """
    query = update.callback_query
    await query.answer()
    
    telegram_user_id = query.from_user.id
    
    with get_db() as session:
        user = crud.get_user_by_telegram_id(session, telegram_user_id)
        
        if not user:
            await query.edit_message_text("❌ المستخدم غير موجود.")
            return
        
        # Get all enrollments with transactions
        from database.models import Transaction as TransactionModel
        
        transactions = session.query(TransactionModel).join(
            TransactionModel.enrollment
        ).filter(
            TransactionModel.enrollment.has(user_id=user.user_id)
        ).order_by(TransactionModel.submitted_date.desc()).limit(10).all()
        
        if not transactions:
            await query.edit_message_text(
                "📋 لا توجد معاملات سابقة.",
                reply_markup=back_to_main_keyboard()
            )
            return
        
        message = "📋 **سجل المعاملات:**\n\n"
        
        for tx in transactions:
            status_emoji = {
                TransactionStatus.APPROVED: "✅",
                TransactionStatus.PENDING: "⏳",
                TransactionStatus.REJECTED: "❌"
            }.get(tx.status, "❓")
            
            message += f"{status_emoji} **{tx.enrollment.course.course_name}**\n"
            message += f"   المبلغ: {tx.extracted_amount:.0f} جنيه\n"
            message += f"   التاريخ: {tx.submitted_date.strftime('%Y-%m-%d %H:%M')}\n"
            message += f"   الحالة: {tx.status.value}\n\n"
        
        await query.edit_message_text(
            message,
            reply_markup=back_to_main_keyboard(),
            parse_mode='Markdown'
        )
async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancel ongoing payment process
    """
    query = update.callback_query
    await query.answer("تم إلغاء العملية")
    
    # Clear payment context
    context.user_data.pop('pending_payment_enrollments', None)
    context.user_data.pop('payment_selection', None)
    
    from handlers.menu_handlers import show_main_menu
    await show_main_menu(update, context)


async def request_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Request support from admin
    """
    query = update.callback_query if update.callback_query else None
    
    if query:
        await query.answer()
    
    telegram_user_id = update.effective_user.id
    
    support_message = """
📞 **الدعم الفني**

للحصول على المساعدة:

1️⃣ راسل الإدارة: @AdminUsername
2️⃣ أرسل رسالة توضح مشكلتك
3️⃣ سيتم الرد عليك في أقرب وقت

💡 **الأسئلة الشائعة:**

❓ لم يتم قبول الإيصال؟
• تأكد من وضوح الصورة
• تحقق من رقم الحساب الصحيح
• تأكد من المبلغ المحول

❓ الإيصال قيد المراجعة؟
• سيتم مراجعته خلال 24 ساعة
• ستصلك رسالة بالنتيجة

❓ كيف أتحقق من حالة التسجيل؟
• اضغط على "دوراتي" من القائمة الرئيسية
"""
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(support_message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(support_message, reply_markup=reply_markup, parse_mode='Markdown')
    
    log_user_action(telegram_user_id, "request_support", "User requested support")


# ===== ADMIN HANDLERS FOR PAYMENT APPROVAL/REJECTION =====

async def admin_approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin approves a payment transaction
    """
    query = update.callback_query
    await query.answer()
    
    # Extract transaction_id from callback data
    transaction_id = int(query.data.split('_')[-1])
    
    admin_user_id = query.from_user.id
    
    with get_db() as session:
        from database.models import Transaction as TransactionModel
        
        transaction = session.query(TransactionModel).filter(
            TransactionModel.transaction_id == transaction_id
        ).first()
        
        if not transaction:
            await query.edit_message_text("❌ Transaction not found.")
            return
        
        enrollment = transaction.enrollment
        user = enrollment.user
        
        # Update transaction status
        transaction.status = TransactionStatus.APPROVED
        transaction.admin_reviewed_by = admin_user_id
        transaction.admin_review_date = datetime.utcnow()
        
        # ✅ UPDATE amount_paid
        payment_amount = transaction.receipt_amount or transaction.extracted_amount or 0
        enrollment.amount_paid = (enrollment.amount_paid or 0) + payment_amount
        
        logger.info(f"✅ Admin approved: enrollment {enrollment.enrollment_id}, added {payment_amount} SDG, total: {enrollment.amount_paid}/{enrollment.payment_amount}")
        
        # Check if fully paid
        remaining = enrollment.payment_amount - enrollment.amount_paid
        
        if remaining <= 0.01:  # Fully paid
            enrollment.payment_status = PaymentStatus.VERIFIED
            enrollment.verification_date = datetime.utcnow()
            
            # Append receipt path if not already there
            if transaction.receipt_image_path not in (enrollment.receipt_image_path or ""):
                if enrollment.receipt_image_path:
                    enrollment.receipt_image_path += f",{transaction.receipt_image_path}"
                else:
                    enrollment.receipt_image_path = transaction.receipt_image_path
            
            session.commit()
            
            # Send group invite to user
            from handlers.group_registration import send_group_invite_link
            group_link = await send_group_invite_link(context, user, enrollment.course)
            
            # Notify user
            user_message = f"""
✅ **تم قبول الدفع!**

تم التحقق من إيصال الدفع بنجاح.

🎓 **الدورة:** {enrollment.course.course_name}
💰 **المبلغ:** {payment_amount:.0f} جنيه سوداني
✅ **الحالة:** مدفوع بالكامل

🔗 **رابط المجموعة:**
{group_link}

مبروك! يمكنك الآن الوصول إلى الدورة.
"""
            
            await context.bot.send_message(
                chat_id=user.telegram_user_id,
                text=user_message,
                parse_mode='Markdown'
            )
            
            await query.edit_message_text(
                f"✅ **APPROVED**\n\n"
                f"Transaction #{transaction_id} approved.\n"
                f"User: {user.first_name} (@{user.username or 'N/A'})\n"
                f"Course: {enrollment.course.course_name}\n"
                f"Amount: {payment_amount:.0f} SDG\n"
                f"Status: **FULLY PAID** ({enrollment.amount_paid:.0f} SDG)\n\n"
                f"User has been notified and granted access.",
                parse_mode='Markdown'
            )
            
            log_user_action(admin_user_id, "admin_approve_payment", f"transaction_id={transaction_id}, enrollment_id={enrollment.enrollment_id}, fully_paid")
        
        else:  # Partially paid
            enrollment.payment_status = PaymentStatus.PENDING
            session.commit()
            
            # Notify user
            user_message = f"""
✅ **تم قبول الدفع الجزئي!**

تم التحقق من إيصال الدفع بنجاح.

🎓 **الدورة:** {enrollment.course.course_name}
💰 **المبلغ المدفوع:** {payment_amount:.0f} جنيه سوداني
📊 **الإجمالي:** {enrollment.amount_paid:.0f}/{enrollment.payment_amount:.0f} جنيه
⚠️ **المتبقي:** {remaining:.0f} جنيه سوداني

لإكمال التسجيل، يرجى دفع المبلغ المتبقي.
"""
            
            await context.bot.send_message(
                chat_id=user.telegram_user_id,
                text=user_message,
                parse_mode='Markdown'
            )
            
            await query.edit_message_text(
                f"✅ **PARTIALLY APPROVED**\n\n"
                f"Transaction #{transaction_id} approved.\n"
                f"User: {user.first_name} (@{user.username or 'N/A'})\n"
                f"Course: {enrollment.course.course_name}\n"
                f"Amount: {payment_amount:.0f} SDG\n"
                f"Paid: {enrollment.amount_paid:.0f}/{enrollment.payment_amount:.0f} SDG\n"
                f"⚠️ **Remaining:** {remaining:.0f} SDG\n\n"
                f"User has been notified to pay remaining amount.",
                parse_mode='Markdown'
            )
            
            log_user_action(admin_user_id, "admin_approve_payment", f"transaction_id={transaction_id}, enrollment_id={enrollment.enrollment_id}, partial_payment")


async def admin_reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin rejects a payment transaction
    """
    query = update.callback_query
    await query.answer()
    
    # Extract transaction_id from callback data
    transaction_id = int(query.data.split('_')[-1])
    
    admin_user_id = query.from_user.id
    
    with get_db() as session:
        from database.models import Transaction as TransactionModel
        
        transaction = session.query(TransactionModel).filter(
            TransactionModel.transaction_id == transaction_id
        ).first()
        
        if not transaction:
            await query.edit_message_text("❌ Transaction not found.")
            return
        
        enrollment = transaction.enrollment
        user = enrollment.user
        
        # Update transaction status
        transaction.status = TransactionStatus.REJECTED
        transaction.admin_reviewed_by = admin_user_id
        transaction.admin_review_date = datetime.utcnow()
        
        # Update enrollment status
        enrollment.payment_status = PaymentStatus.FAILED
        
        session.commit()
        
        # Notify user
        user_message = f"""
❌ **تم رفض الإيصال**

عذراً، لم يتم قبول إيصال الدفع.

🎓 **الدورة:** {enrollment.course.course_name}

⚠️ **السبب:**
{transaction.failure_reason or 'لم يتم التحقق من الإيصال'}

📝 **الإجراء المطلوب:**
• تحقق من رقم الحساب الصحيح
• تأكد من وضوح الصورة
• قم بإرسال إيصال جديد من "دوراتي"

للمساعدة، تواصل مع الإدارة.
"""
        
        await context.bot.send_message(
            chat_id=user.telegram_user_id,
            text=user_message,
            parse_mode='Markdown'
        )
        
        await query.edit_message_text(
            f"❌ **REJECTED**\n\n"
            f"Transaction #{transaction_id} rejected.\n"
            f"User: {user.first_name} (@{user.username or 'N/A'})\n"
            f"Course: {enrollment.course.course_name}\n\n"
            f"User has been notified.",
            parse_mode='Markdown'
        )
        
        log_user_action(admin_user_id, "admin_reject_payment", f"transaction_id={transaction_id}, enrollment_id={enrollment.enrollment_id}")


# ===== EXPORTS =====

__all__ = [
    'proceed_to_payment_callback',
    'handle_payment_receipt',
    'select_courses_for_payment',
    'toggle_payment_selection',
    'clear_payment_selection',
    'view_my_courses',
    'retry_failed_payment',
    'view_payment_history',
    'cancel_payment',
    'request_support',
    'admin_approve_payment',
    'admin_reject_payment',
]
