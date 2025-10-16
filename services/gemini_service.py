# services/gemini_service.py
"""
Google Gemini Vision AI service for receipt validation
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

async def validate_receipt_with_gemini_ai(image_path: str, expected_amount: float, expected_account: str, max_retries: int = 1) -> Dict[str, Any]:
    """
    Validate receipt using Google Gemini Vision AI with retry logic and STRICT account validation
    
    Args:
        image_path: Path to the receipt image
        expected_amount: Expected payment amount in SDG
        expected_account: Expected account number (MUST match exactly)
        max_retries: Maximum number of retry attempts (default: 1)
    
    Returns:
        Dictionary with validation results
    """
    
    # Get current date for validation
    current_date = datetime.now()
    current_date_str = current_date.strftime("%Y-%m-%d")
    max_acceptable_date = (current_date + timedelta(days=1)).strftime("%Y-%m-%d")  # Allow 1 day tolerance for timezone
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Gemini validation attempt {attempt + 1}/{max_retries} for image: {image_path}")
            
            # Open and prepare the image
            image = Image.open(image_path)
            
            # Create the prompt for receipt validation with STRICT account check and date validation
            prompt = f"""
Analyze this payment receipt image and extract the following information in JSON format:

{{
  "account_number": "extracted account number or recipient info",
  "amount": extracted payment amount as a number,
  "date": "payment date in YYYY-MM-DD format if visible",
  "transaction_id": "transaction/reference number if visible",
  "currency": "detected currency (likely SDG - Sudanese Pound)",
  "is_valid": true or false,
  "validation_notes": "brief explanation (max 80 words)",
  "tampering_indicators": [
    "list any visual signs of editing or fraud (empty array if none)"
  ],
  "authenticity_score": 0-100
}}

**CRITICAL Validation Rules:**

1. **ACCOUNT NUMBER**: The 'To Account' or recipient account MUST EXACTLY match: {expected_account}
   - If it doesn't match EXACTLY, set is_valid to FALSE immediately
   - Check all account number fields in the receipt

2. **AMOUNT**: Must be at least {expected_amount:.2f} SDG (allow 2% tolerance = {expected_amount * 0.98:.2f} SDG minimum)

3. **DATE VALIDATION**: 
   - Current date: {current_date_str}
   - Receipt date CANNOT be in the future (after {max_acceptable_date})
   - If date is future or invalid, add to tampering_indicators and set is_valid FALSE
   - Very old dates (>6 months) should also be flagged in tampering_indicators

4. **VISUAL AUTHENTICITY CHECKS** (add to tampering_indicators if found):
   - Text appears digitally added or overlaid
   - Unnatural fonts, sizes, or alignments
   - Inconsistent lighting or shadows around text
   - Different text quality in critical fields (account, amount)
   - Misaligned text not following receipt's grid
   - White/colored boxes behind text
   - Signs of copy-paste or cloning

5. **LOGICAL CONSISTENCY**:
   - Do line items add up correctly?
   - Are tax calculations correct?
   - Does format look authentic for this bank?

**Decision Rules:**
- Set "is_valid" to FALSE if:
  * Account doesn't match EXACTLY
  * Amount is below {expected_amount * 0.98:.2f} SDG
  * Date is in the future
  * 2+ tampering indicators detected
  * Authenticity score < 60

**Authenticity Score Guidelines:**
- 90-100: Perfect, no signs of tampering
- 70-89: Minor concerns but likely authentic
- 50-69: Multiple suspicious elements
- 0-49: Clear signs of forgery/editing

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
            tampering_indicators = data.get("tampering_indicators", [])
            authenticity_score = data.get("authenticity_score", 100)
            
            # ADDITIONAL STRICT CHECK on our side - Account Number
            if account_number and expected_account:
                # Normalize both (remove spaces, dashes, etc)
                normalized_extracted = ''.join(filter(str.isdigit, str(account_number)))
                normalized_expected = ''.join(filter(str.isdigit, str(expected_account)))
                
                if normalized_extracted != normalized_expected:
                    logger.warning(f"Account mismatch: Expected {normalized_expected}, Got {normalized_extracted}")
                    is_valid = False
                    validation_notes = f"رقم الحساب غير صحيح. المطلوب: {expected_account}, المستلم: {account_number}"
            
            # ADDITIONAL STRICT CHECK - Date Validation
            if extracted_date:
                try:
                    # Try to parse the date
                    receipt_date = datetime.strptime(extracted_date, "%Y-%m-%d")
                    
                    # Check if date is in the future
                    if receipt_date > current_date + timedelta(days=1):
                        logger.warning(f"Future date detected: {extracted_date} (current: {current_date_str})")
                        is_valid = False
                        tampering_indicators.append(f"Future date detected: {extracted_date}")
                        validation_notes = f"التاريخ في المستقبل! التاريخ: {extracted_date}, اليوم: {current_date_str}"
                    
                    # Check if date is very old (>6 months)
                    elif receipt_date < current_date - timedelta(days=180):
                        logger.warning(f"Very old date detected: {extracted_date}")
                        tampering_indicators.append(f"Receipt date is over 6 months old: {extracted_date}")
                        
                except ValueError:
                    logger.warning(f"Invalid date format: {extracted_date}")
                    tampering_indicators.append(f"Invalid date format: {extracted_date}")
            
            # Build result
            result = {
                "is_valid": bool(is_valid),
                "account_number": str(account_number) if account_number else None,
                "amount": float(amount) if amount else None,
                "date": extracted_date,
                "transaction_id": data.get("transaction_id"),
                "currency": data.get("currency", "SDG"),
                "reason": validation_notes if not is_valid else "تم التحقق من الدفع بنجاح",
                "tampering_indicators": tampering_indicators,
                "authenticity_score": authenticity_score,
                "raw_response": response_text
            }
            
            logger.info(f"Gemini validation completed successfully on attempt {attempt + 1}")
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
                    "amount": None,
                    "date": None,
                    "transaction_id": None,
                    "currency": "SDG",
                    "reason": f"فشل التحقق التلقائي. يتطلب مراجعة يدوية. خطأ: {str(e)}",
                    "tampering_indicators": [],
                    "authenticity_score": 0,
                    "raw_response": None
                }
            
            # Wait before retry with exponential backoff
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            logger.info(f"Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)
    
    # Should never reach here, but just in case
    return {
        "is_valid": False,
        "requires_manual_review": True,
        "account_number": None,
        "amount": None,
        "reason": "فشل التحقق - يتطلب مراجعة يدوية",
        "tampering_indicators": [],
        "authenticity_score": 0,
        "raw_response": None
    }
