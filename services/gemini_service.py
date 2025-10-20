# services/gemini_service.py

"""
Google Gemini Vision AI service for receipt validation with FUZZY matching
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

# Initialize the model
model = genai.GenerativeModel('gemini-2.5-flash')


async def validate_receipt_with_gemini_ai(
    image_path: str, 
    expected_amount: float, 
    expected_account: str, 
    max_retries: int = 1
) -> Dict[str, Any]:
    """
    Validate receipt using Google Gemini Vision AI with FLEXIBLE/FUZZY matching
    
    Args:
        image_path: Path to the receipt image
        expected_amount: Expected payment amount in SDG
        expected_account: Expected account number (fuzzy match acceptable)
        max_retries: Maximum number of retry attempts (default: 1)
    
    Returns:
        Dictionary with validation results including metadata for duplicate detection
    """
    # Get current date for validation
    current_date = datetime.now()
    current_date_str = current_date.strftime("%Y-%m-%d")
    max_acceptable_date = (current_date + timedelta(days=1)).strftime("%Y-%m-%d")
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Gemini validation attempt {attempt + 1}/{max_retries} for image: {image_path}")
            
            # Open and prepare the image
            image = Image.open(image_path)
            
            # Enhanced prompt with FUZZY matching instructions
            prompt = f"""
Analyze this payment receipt image and extract the following information in JSON format:

{{
  "account_number": "extracted account number or recipient info",
  "amount": extracted payment amount as a number,
  "date": "payment date in YYYY-MM-DD format if visible",
  "transaction_id": "transaction/reference number if visible (can be ANY field that looks like a unique ID)",
  "sender_name": "sender/payer name if visible",
  "sender_account": "sender account number if visible",
  "currency": "detected currency (likely SDG - Sudanese Pound)",
  "is_valid": true or false,
  "validation_notes": "brief explanation (max 80 words)",
  "account_match_confidence": 0-100,
  "amount_match_confidence": 0-100,
  "tampering_indicators": [
    "list any visual signs of editing or fraud (empty array if none)"
  ],
  "authenticity_score": 0-100
}}

**FLEXIBLE Validation Rules:**

1. **ACCOUNT NUMBER** (FUZZY matching - be LENIENT):
   - Target account: {expected_account}
   - Look for fields like: "To Account", "Recipient", "Beneficiary", "Account Number", "رقم الحساب", "المستفيد"
   - Accept if account CONTAINS or IS CONTAINED IN the target (partial match OK)
   - Remove spaces, dashes, and special characters before comparing
   - If last 4-6 digits match, that's acceptable
   - Set account_match_confidence (0-100):
     * 100: Perfect exact match
     * 80-99: Very close (last 6+ digits match, or same with formatting differences)
     * 60-79: Reasonable match (last 4-5 digits match, or similar pattern)
     * 40-59: Weak match (some similarity detected)
     * 0-39: No meaningful match
   - Only reject if confidence < 40

2. **AMOUNT** (FLEXIBLE tolerance):
   - Expected: {expected_amount:.2f} SDG
   - Accept if within 5% tolerance: {expected_amount * 0.95:.2f} to {expected_amount * 1.05:.2f} SDG
   - Set amount_match_confidence (0-100):
     * 100: Exact match
     * 90-99: Within 1%
     * 80-89: Within 2-3%
     * 70-79: Within 5%
     * 0-69: Outside acceptable range

3. **DATE VALIDATION** (reject only if clearly wrong):
   - Current date: {current_date_str}
   - Receipt date CANNOT be in the future (after {max_acceptable_date})
   - Old dates (even 1+ years) are OK - don't reject unless clearly fake
   - Only flag very old dates (>2 years) in tampering_indicators as INFO, not rejection

4. **TRANSACTION ID EXTRACTION** (CRITICAL - be FLEXIBLE):
   - Look for ANY field that could be a unique identifier:
     * Transaction ID, Reference Number, Operation Number, Receipt Number
     * Any alphanumeric code that looks unique (e.g., "TXN123456", "REF-2024-001")
     * Even internal reference numbers are OK
   - Extract even if format is unusual - we just need SOMETHING unique for duplicate detection

5. **SENDER INFORMATION** (extract if visible, don't require):
   - sender_name: Any name associated with "From", "Sender", "Payer", "المرسل"
   - sender_account: Sender's account if visible
   - These are optional - set to null if not found

6. **VISUAL AUTHENTICITY CHECKS** (only flag OBVIOUS tampering):
   - Add to tampering_indicators ONLY if signs are clear:
     * Very obvious Photoshop artifacts
     * Completely misaligned text
     * Different font/style in critical fields
     * Clear copy-paste evidence
   - Be LENIENT - low-quality images, blurry text, or poor formatting is NOT tampering

**Decision Rules (RELAXED):**
- Set "is_valid" to TRUE if:
  * account_match_confidence >= 40 (or no account found in receipt)
  * amount_match_confidence >= 70
  * Date is not in future
  * authenticity_score >= 50
  * Less than 3 CLEAR tampering indicators

- Set "is_valid" to FALSE only if:
  * account_match_confidence < 40 AND account was clearly visible
  * amount_match_confidence < 70
  * Date is in the future
  * authenticity_score < 50
  * 3+ obvious tampering indicators

**Authenticity Score Guidelines (LENIENT):**
- 80-100: Looks legitimate (even if low quality)
- 60-79: Some concerns but probably real
- 40-59: Multiple suspicious elements
- 0-39: Clear signs of forgery

**IMPORTANT**: When in doubt, ACCEPT the receipt (set is_valid=true). Only reject if you're CONFIDENT it's fake.

Return ONLY the JSON object, no other text.
"""
            
            # Generate content
            logger.debug(f"Sending image to Gemini API: {image_path}")
            response = model.generate_content([prompt, image])
            
            # Extract and clean the response text
            response_text = response.text.strip()
            logger.debug(f"Gemini raw response: {response_text[:200]}...")
            
            # Remove markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = response_text[7:].strip()
            elif response_text.startswith("```"):
                response_text = response_text[3:].strip()
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()
            
            # Parse JSON response
            try:
                data = json.loads(response_text)
                logger.info(f"Gemini validation successful: is_valid={data.get('is_valid')}, amount={data.get('amount')}")
            except json.JSONDecodeError as json_err:
                logger.error(f"Failed to parse Gemini JSON response: {json_err}")
                logger.error(f"Response text: {response_text}")
                raise ValueError(f"Invalid JSON response from Gemini: {json_err}")
            
            # Extract validation result
            is_valid = data.get("is_valid", False)
            account_number = data.get("account_number", "")
            amount = data.get("amount", 0)
            validation_notes = data.get("validation_notes", "")
            extracted_date = data.get("date")
            transaction_id = data.get("transaction_id", "")
            sender_name = data.get("sender_name", "")
            sender_account = data.get("sender_account", "")
            tampering_indicators = data.get("tampering_indicators", [])
            authenticity_score = data.get("authenticity_score", 100)
            account_match_confidence = data.get("account_match_confidence", 50)
            amount_match_confidence = data.get("amount_match_confidence", 50)
            
            # Python-side FUZZY validation (just in case Gemini is too strict)
            receipt_datetime = None
            if extracted_date:
                try:
                    receipt_datetime = datetime.strptime(extracted_date, "%Y-%m-%d")
                    
                    # Only reject if CLEARLY in the future
                    if receipt_datetime > current_date + timedelta(days=1):
                        logger.warning(f"Future date detected: {extracted_date}")
                        is_valid = False
                        validation_notes = f"التاريخ في المستقبل! {extracted_date}"
                    
                except ValueError:
                    logger.warning(f"Invalid date format: {extracted_date}, but continuing...")
            
            # Build result with enhanced metadata
            result = {
                "is_valid": bool(is_valid),
                "account_number": str(account_number) if account_number else None,
                "account_match_confidence": account_match_confidence,
                "amount": float(amount) if amount else None,
                "amount_match_confidence": amount_match_confidence,
                "date": extracted_date,
                "transfer_datetime": receipt_datetime,
                "transaction_id": transaction_id if transaction_id else None,
                "sender_name": sender_name if sender_name else None,
                "sender_account": sender_account if sender_account else None,
                "currency": data.get("currency", "SDG"),
                "reason": validation_notes if not is_valid else "تم التحقق من الدفع بنجاح ✅",
                "tampering_indicators": tampering_indicators,
                "authenticity_score": authenticity_score,
                "raw_response": response_text
            }
            
            logger.info(f"✅ Gemini validation completed on attempt {attempt + 1}")
            logger.info(f"📊 Scores - Account: {account_match_confidence}%, Amount: {amount_match_confidence}%, Auth: {authenticity_score}%")
            logger.info(f"📋 Metadata - TxID: {transaction_id}, Sender: {sender_name}, Date: {extracted_date}")
            return result
            
        except Exception as e:
            logger.error(f"Gemini API attempt {attempt + 1}/{max_retries} failed: {type(e).__name__}: {e}")
            
            # If this was the last attempt, return failure result
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} Gemini validation attempts failed for {image_path}")
                return {
                    "is_valid": False,
                    "requires_manual_review": True,
                    "account_number": None,
                    "account_match_confidence": 0,
                    "amount": None,
                    "amount_match_confidence": 0,
                    "date": None,
                    "transfer_datetime": None,
                    "transaction_id": None,
                    "sender_name": None,
                    "sender_account": None,
                    "currency": "SDG",
                    "reason": f"فشل التحقق التلقائي - يتطلب مراجعة يدوية ⚠️",
                    "tampering_indicators": [],
                    "authenticity_score": 0,
                    "raw_response": None
                }
            
            # Wait before retry
            wait_time = 2 ** attempt
            logger.info(f"Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)
    
    return {
        "is_valid": False,
        "requires_manual_review": True,
        "reason": "فشل التحقق - يتطلب مراجعة يدوية",
        "raw_response": None
    }
