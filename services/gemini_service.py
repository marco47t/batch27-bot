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


def match_account_number(extracted_account: str, expected_accounts: list) -> tuple:
    """
    Match extracted account against multiple expected accounts with partial matching
    Handles masked formats like xxxx163485xxxx
    
    Args:
        extracted_account: Account number extracted from receipt (may be masked)
        expected_accounts: List of valid account numbers to check against
    
    Returns:
        tuple: (matched, confidence_score)
    """
    if not extracted_account:
        return False, 0
    
    # Clean extracted account (remove spaces, asterisks, x's, dashes)
    cleaned = ''.join(c for c in extracted_account if c.isdigit())
    
    if not cleaned:
        return False, 0
    
    best_confidence = 0
    matched = False
    
    for expected in expected_accounts:
        expected_clean = expected.strip()
        
        # Perfect match
        if expected_clean == cleaned:
            logger.info(f"✅ Perfect account match: {expected_clean}")
            return True, 100
        
        # Check if expected number is contained in extracted (handles xxxx163485xxxx)
        if expected_clean in cleaned:
            logger.info(f"✅ Account found in masked format: {expected_clean} in {cleaned}")
            matched = True
            best_confidence = max(best_confidence, 90)
            continue
        
        # Check if extracted is contained in expected (rare but possible)
        if cleaned in expected_clean:
            logger.info(f"✅ Partial account match: {cleaned} in {expected_clean}")
            matched = True
            best_confidence = max(best_confidence, 85)
            continue
        
        # Check if extracted is contained in expected (rare but possible)
        if cleaned in expected_clean:
            logger.info(f"✅ Partial account match: {cleaned} in {expected_clean}")
            matched = True
            best_confidence = max(best_confidence, 85)
            continue
        
        # Check last 6 digits
        if len(cleaned) >= 6 and len(expected_clean) >= 6:
            if cleaned[-6:] == expected_clean[-6:]:
                logger.info(f"✅ Last 6 digits match: {cleaned[-6:]} == {expected_clean[-6:]}")
                matched = True
                best_confidence = max(best_confidence, 80)
                continue
        
        # Check first 6 digits
        if len(cleaned) >= 6 and len(expected_clean) >= 6:
            if cleaned[:6] == expected_clean[:6]:
                logger.info(f"✅ First 6 digits match: {cleaned[:6]} == {expected_clean[:6]}")
                matched = True
                best_confidence = max(best_confidence, 75)
                continue
        
        # Fuzzy match: count matching digit positions
        min_len = min(len(cleaned), len(expected_clean))
        matches = sum(1 for i in range(min_len) if cleaned[i] == expected_clean[i])
        
        if matches >= 4:  # At least 4 consecutive matching digits
            match_ratio = (matches / max(len(cleaned), len(expected_clean))) * 100
            if match_ratio >= 40:
                logger.info(f"⚠️ Fuzzy account match: {matches} digits match ({match_ratio:.1f}%)")
                matched = True
                best_confidence = max(best_confidence, int(match_ratio))
    
    if not matched:
        logger.warning(f"❌ No account match found for: {extracted_account} (cleaned: {cleaned})")
    
    return matched, best_confidence


async def validate_receipt_with_gemini_ai(
    image_path: str,
    expected_amount: float,
    expected_accounts: list,  # ✅ NOW ACCEPTS LIST
    max_retries: int = 1
) -> Dict[str, Any]:
    """
    Validate receipt with OLD receipt detection and multilingual field extraction
    
    Args:
        image_path: Path to the receipt image
        expected_amount: Expected MINIMUM payment amount in SDG
        expected_accounts: List of expected account numbers (supports multiple + masked formats)
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
  "amount": extracted amount as number,
  "date": "payment date in YYYY-MM-DD format",
  "time": "payment time if visible (HH:MM format)",
  "transaction_id": "unique transaction identifier",
  "sender_name": "payer/sender name",
  "recipient_name": "beneficiary/recipient name",
  "sender_account": "sender account number",
  "currency": "detected currency",
  "is_valid": true or false,
  "validation_notes": "explanation (max 60 words)",
  "account_match_confidence": 0-100,
  "amount_match_confidence": 0-100,
  "days_since_transfer": estimated days between transfer date and today,
  "tampering_indicators": [],
  "authenticity_score": 0-100
}}

**FLEXIBLE Validation Rules:**

1. **ACCOUNT NUMBER** (flexible partial matching):
- Target accounts (accept ANY of these): {', '.join(expected_accounts)}
- Look for fields: "To Account", "Recipient", "Beneficiary", "إلى حساب", "المستفيد", "رقم الحساب"
- **IMPORTANT FORMATS TO HANDLE:**
  * Full number: "163485"
  * Masked format: "xxxx163485xxxx" or "****163485****"
  * Partial: "...63485" or "163485..."
  * With spaces: "16 34 85"
- **Matching Rules:**
  * Extract ANY continuous digit sequence from account field
  * Check if it CONTAINS any of the target numbers
  * Accept if ANY target number is found within the extracted sequence
  * Set account_match_confidence:
    - 100: Exact match or full number found
    - 90: Found in masked format (xxxx{{number}}xxxx)
    - 70: Partial match (4+ consecutive digits match)
    - 40: Fuzzy match (some digits match)
    - 0: No match
- Only reject if confidence < 40

 **AMOUNT** (ACCEPT ANY POSITIVE AMOUNT - Partial payments allowed):
   - Expected: {expected_amount:.2f} SDG
   - ✅ ACCEPT ANY amount > 0 (including partial payments)
   - Partial payments are NORMAL and expected in this system
   - Set amount_match_confidence:
     * 100: Exact match or higher
     * 95: Close to expected (within 5%)
     * 75: Partial payment (50-95% of expected)
     * 50: Low partial payment (<50% of expected)
   - **NEVER reject based on amount** - system handles partial payments automatically

3. **DATE & TIME EXTRACTION** (multilingual - CRITICAL):
   - Look for fields labeled:
     * English: "Date", "Transfer Date", "Transaction Date", "Date/Time"
     * Arabic: "التاريخ", "تاريخ التحويل", "التاريخ والزمن", "التاريخ والوقت"
   - Extract date in YYYY-MM-DD format
   - Extract time if visible (HH:MM format)
   - **OLD RECEIPT DETECTION** (IMPORTANT):
     * Today's date: {current_date_str}
     * Flag threshold: {old_receipt_threshold} (5 days ago)
     * Calculate "days_since_transfer": How many days between receipt date and today
     * If receipt date is BEFORE {old_receipt_threshold} (>5 days old), add to tampering_indicators:
       "Receipt is {{X}} days old - transfer made on {{date}} but submitted today ({current_date_str})"

4. **TRANSACTION ID** (multilingual extraction - CRITICAL):
   - Look for ANY unique identifier with labels like:
     * English: "Transaction ID", "Reference Number", "Receipt Number", "Operation Number", "Ref No", "TXN ID"
     * Arabic: "رقم العملية", "رقم المرجع", "رقم الإيصال", "الرقم المرجعي", "معرف العملية"
   - Extract the VALUE (not the label), e.g., if you see "رقم العملية: 123456", extract "123456"
   - Accept ANY alphanumeric format (numbers, letters, dashes, combinations)
   - This is MANDATORY for duplicate detection - extract even if format is unusual

5. **SENDER & RECIPIENT NAMES** (multilingual):
   - **sender_name**: Look for:
     * "From", "Sender", "Payer", "Account Holder"
     * "من", "المرسل", "الدافع", "صاحب الحساب"
   - **recipient_name**: Look for:
     * "To", "Recipient", "Beneficiary", "Payee"
     * "إلى", "المستفيد", "المستلم"
   - Extract BOTH if visible (one may be missing)
   - If sender_name is not found, use recipient_name as fallback

6. **VISUAL AUTHENTICITY** (lenient):
   - Only flag OBVIOUS signs of tampering:
     * Clear Photoshop artifacts
     * Completely misaligned text
     * Different fonts in critical fields
   - Low quality images are NOT tampering

**Decision Rules:**
- Set "is_valid" to TRUE if:
  * account_match_confidence >= 40
  * amount > 0 (any positive amount accepted - partial payments OK)
  * authenticity_score >= 50
  * Less than 3 clear tampering indicators
  * (Old receipts are flagged but NOT rejected)

- Set "is_valid" to FALSE only if:
  * account_match_confidence < 40 (and account was clearly visible)
  * amount <= 0 or not found
  * authenticity_score < 50
  * 3+ obvious tampering signs

**IMPORTANT**: 
- Accept receipts even if they're old (just flag in tampering_indicators)
- Accept ANY positive amount (partial payments are handled by system)
- DO NOT add partial payment warnings to tampering_indicators
- Extract Arabic field names (رقم العملية, التاريخ والزمن, etc.)

Return ONLY the JSON object.
"""
            
            # Generate response
            logger.debug(f"Sending to Gemini: {image_path}")
            # Run Gemini in a separate thread to avoid blocking the asyncio event loop.
            # The `run_in_executor` function runs the specified function in a separate
            # thread, which prevents it from blocking the main asyncio event loop.
            # This is the recommended way to run blocking I/O operations in an
            # asyncio application.
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,  # Use default ThreadPoolExecutor
                lambda: model.generate_content([prompt, image])
            )

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
            
            # ✅ Python-side account validation (double-check Gemini's result)
            extracted_account = data.get("account_number", "")
            if extracted_account:
                matched, confidence = match_account_number(extracted_account, expected_accounts)
                
                # Log the match result
                logger.info(f"🏦 Account validation: extracted='{extracted_account}', matched={matched}, confidence={confidence}%")
                
                # Override Gemini's confidence if our matching is better
                gemini_confidence = data.get("account_match_confidence", 0)
                if confidence > gemini_confidence:
                    logger.info(f"   Overriding Gemini confidence {gemini_confidence}% → {confidence}%")
                    data["account_match_confidence"] = confidence
                
                # Update validity based on account match
                if not matched and confidence < 40:
                    is_valid = False
                    tampering_indicators.append(f"Account number mismatch: found '{extracted_account}', expected one of {expected_accounts}")
                    logger.warning(f"❌ Account validation FAILED: {extracted_account} not in {expected_accounts}")
            
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
