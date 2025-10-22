# services/gemini_service.py

"""
Google Gemini Vision AI service for receipt validation with old receipt detection
"""

import json
import os
from typing import Dict, Any
from datetime import datetime, timedelta
import google.generativeai as genai
from PIL import Image
import config
import asyncio
import logging

logger = logging.getLogger(__name__)

# Configure Gemini API
genai.configure(api_key=config.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')


async def validate_receipt_with_gemini_ai(
    image_path: str, 
    expected_amount: float, 
    expected_account: str, 
    max_retries: int = 1
) -> Dict[str, Any]:
    """
    Validate receipt with OLD receipt detection and multilingual field extraction
    
    Args:
        image_path: Path to the receipt image
        expected_amount: Expected MINIMUM payment amount in SDG
        expected_account: Expected account number (fuzzy match)
        max_retries: Maximum retry attempts
    
    Returns:
        Dict with validation results and metadata for duplicate detection
    """
    # Calculate dates for validation
    current_date = datetime.now()
    current_date_str = current_date.strftime("%Y-%m-%d")
    old_receipt_threshold = (current_date - timedelta(days=5)).strftime("%Y-%m-%d")
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Gemini validation attempt {attempt + 1}/{max_retries} for image: {image_path}")
            
            image = Image.open(image_path)
            
            # Enhanced prompt with multilingual and old receipt detection
            prompt = f"""
Analyze this payment receipt and extract information in JSON format:
{{
  "account_number": "extracted account/recipient info",
  "amount": "extracted amount as number",
  "date": "payment date in YYYY-MM-DD format",
  "time": "payment time if visible (HH:MM format)",
  "transaction_id": "unique transaction identifier",
  "sender_name": "payer/sender name",
  "recipient_name": "beneficiary/recipient name",
  "sender_account": "sender account number",
  "currency": "detected currency",
  "is_valid": true or false,
  "validation_notes": "explanation (max 60 words)",
  "account_match_confidence": "0-100",
  "amount_match_confidence": "0-100",
  "days_since_transfer": "estimated days between transfer date and today",
  "tampering_indicators": [],
  "authenticity_score": "0-100"
}}

FLEXIBLE Validation Rules:

1. ACCOUNT NUMBER (fuzzy match):
   - Target: {expected_account}
   - Look for "To Account", "Recipient", "Beneficiary", "المستفيد", "إلى حساب", "الحساب"
   - Accept partial matches (last 4-6 digits OK)
   - Set account_match_confidence based on similarity
   - Only reject if confidence < 40%

2. AMOUNT - ACCEPT ANY AMOUNT (including partial payments):
   - Expected: {expected_amount:.2f} SDG
   - ALWAYS ACCEPT ANY AMOUNT >= 0
   - PARTIAL PAYMENTS ARE VALID - user will pay remainder later
   - Set amount_match_confidence:
     * 100: Exact match or higher
     * 95: Close to expected (within 5%)
     * 50: Partial payment (below expected)
   - NEVER reject based on amount alone

3. DATE/TIME EXTRACTION (multilingual):
   - Look for "Date", "Transfer Date", "Transaction Date", "التاريخ", "تاريخ التحويل"
   - Extract date in YYYY-MM-DD format
   - Extract time if visible (HH:MM format)
   - Calculate days_since_transfer

4. TRANSACTION ID (multilingual extraction):
   - Look for "Transaction ID", "Reference Number", "Receipt Number", "رقم العملية", "رقم المرجع"
   - Extract the VALUE (e.g., "123456")
   - Accept ANY alphanumeric format
   - MANDATORY for duplicate detection

5. SENDER/RECIPIENT NAMES (multilingual):
   - sender_name: Look for "From", "Sender", "Payer", "من", "المرسل"
   - recipient_name: Look for "To", "Recipient", "Beneficiary", "إلى", "المستفيد"
   - Extract BOTH if visible

6. VISUAL AUTHENTICITY (lenient):
   - Only flag OBVIOUS tampering:
     * Clear Photoshop artifacts
     * Completely misaligned text
     * Different fonts in critical fields
   - Low quality/screenshots are NOT tampering

Decision Rules:
- Set is_valid to TRUE if:
  * account_match_confidence >= 40% OR account not clearly visible
  * amount > 0 (ANY amount is valid, even partial)
  * authenticity_score >= 50%
  * Less than 3 clear tampering indicators

- Set is_valid to FALSE only if:
  * account_match_confidence < 40% AND account was clearly visible
  * authenticity_score < 50%
  * 3+ obvious tampering signs

IMPORTANT:
- Accept ANY positive amount (partial payments are allowed)
- Old receipts are flagged but NOT automatically rejected
- Extract Arabic field names (التاريخ, المبلغ, etc.)

Return ONLY the JSON object.
"""
            
            # Generate response
            logger.debug(f"Sending to Gemini: {image_path}")
            response = model.generate_content([prompt, image])
            response_text = response.text.strip()
            
            # Clean response
            if response_text.startswith("```json"):
                response_text = response_text[7:].strip()
            elif response_text.startswith("```"):
                response_text = response_text[3:].strip()
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()
            
            # Parse JSON
            try:
                data = json.loads(response_text)
                logger.info(f"Gemini result: valid={data.get('is_valid')}, amount={data.get('amount')}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}")
                raise ValueError(f"Invalid Gemini JSON: {e}")
            
            # Extract fields
            is_valid = data.get("is_valid", False)
            extracted_date = data.get("date")
            extracted_time = data.get("time")
            transaction_id = data.get("transaction_id", "")
            sender_name = data.get("sender_name", "")
            recipient_name = data.get("recipient_name", "")
            tampering_indicators = data.get("tampering_indicators", [])
            days_since_transfer = data.get("days_since_transfer")
            
            # Parse datetime
            receipt_datetime = None
            if extracted_date:
                try:
                    # Parse date and optionally time
                    if extracted_time:
                        datetime_str = f"{extracted_date} {extracted_time}"
                        receipt_datetime = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
                    else:
                        receipt_datetime = datetime.strptime(extracted_date, "%Y-%m-%d")
                    
                    # Calculate days since transfer (Python-side verification)
                    actual_days_since = (current_date - receipt_datetime).days
                    
                    # Flag if receipt is >5 days old
                    if actual_days_since > 5:
                        old_receipt_warning = f"تحذير: الإيصال قديم - تم التحويل قبل {actual_days_since} أيام في تاريخ {extracted_date}"
                        logger.warning(f"Old receipt detected: {actual_days_since} days old (date: {extracted_date})")
                        if old_receipt_warning not in tampering_indicators:
                            tampering_indicators.append(old_receipt_warning)
                    
                except ValueError as e:
                    logger.warning(f"Date parse error: {extracted_date}, {e}")
            
            # Use recipient_name as fallback if sender_name is missing
            final_sender_name = sender_name if sender_name else recipient_name
            
            # Build result
            result = {
                "is_valid": bool(is_valid),
                "account_number": data.get("account_number"),
                "account_match_confidence": data.get("account_match_confidence", 50),
                "amount": float(data.get("amount")) if data.get("amount") else None,
                "amount_match_confidence": data.get("amount_match_confidence", 50),
                "date": extracted_date,
                "time": extracted_time,
                "transfer_datetime": receipt_datetime,
                "transaction_id": transaction_id if transaction_id else None,
                "sender_name": final_sender_name if final_sender_name else None,
                "recipient_name": recipient_name if recipient_name else None,
                "sender_account": data.get("sender_account"),
                "currency": data.get("currency", "SDG"),
                "reason": data.get("validation_notes", "تم التحقق من الإيصال"),
                "tampering_indicators": tampering_indicators,
                "authenticity_score": data.get("authenticity_score", 100),
                "days_since_transfer": days_since_transfer,
                "raw_response": response_text
            }
            
            logger.info(f"✅ Validation complete - Scores: Acc={result['account_match_confidence']}%, Amt={result['amount_match_confidence']}%, Auth={result['authenticity_score']}%")
            logger.info(f"📋 Metadata: TxID={transaction_id}, Sender={final_sender_name}, Date={extracted_date}, DaysOld={days_since_transfer}")
            
            return result
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            
            if attempt == max_retries - 1:
                # Simple, friendly manual review message (no warnings)
                return {
                    "is_valid": False,
                    "requires_manual_review": True,
                    "account_number": None,
                    "amount": None,
                    "date": None,
                    "transfer_datetime": None,
                    "transaction_id": None,
                    "sender_name": None,
                    "recipient_name": None,
                    "currency": "SDG",
                    "reason": "تم إرسال إيصالك للمراجعة. سيتم الرد عليك قريباً",  # Simple, no warning icons
                    "tampering_indicators": [],
                    "authenticity_score": 0,
                    "raw_response": None
                }
            
            await asyncio.sleep(2 ** attempt)
    
    return {
        "is_valid": False,
        "requires_manual_review": True,
        "reason": "تم إرسال إيصالك للمراجعة",
        "raw_response": None
    }
