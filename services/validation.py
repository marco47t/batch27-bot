"""
Receipt validation utilities and helpers
"""
import re
from typing import Dict, Any, List
from datetime import datetime

def validate_amount_format(amount_str: str) -> float:
    """Extract and validate amount from string"""
    # Remove currency symbols and whitespace
    clean_amount = re.sub(r'[^\d.,]', '', amount_str)
    
    # Handle different decimal separators
    if ',' in clean_amount and '.' in clean_amount:
        # Assume comma is thousands separator
        clean_amount = clean_amount.replace(',', '')
    elif ',' in clean_amount and clean_amount.count(',') == 1:
        # Check if comma might be decimal separator
        parts = clean_amount.split(',')
        if len(parts[1]) <= 2:  # Likely decimal separator
            clean_amount = clean_amount.replace(',', '.')
    
    try:
        return float(clean_amount)
    except ValueError:
        return 0.0

def validate_account_match(extracted: str, expected: str, threshold: float = 0.8) -> bool:
    """Check if extracted account matches expected with fuzzy matching"""
    if not extracted or not expected:
        return False
    
    extracted_clean = re.sub(r'[^\w]', '', extracted.lower())
    expected_clean = re.sub(r'[^\w]', '', expected.lower())
    
    # Exact match
    if extracted_clean == expected_clean:
        return True
    
    # Partial match
    if expected_clean in extracted_clean or extracted_clean in expected_clean:
        return True
    
    # Check if most significant parts match
    expected_parts = [part for part in expected_clean.split() if len(part) > 3]
    matches = sum(1 for part in expected_parts if part in extracted_clean)
    
    return matches / len(expected_parts) >= threshold if expected_parts else False

def extract_date_from_text(text: str) -> str:
    """Extract date from text and normalize to YYYY-MM-DD format"""
    date_patterns = [
        r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b',  # MM/DD/YYYY or DD/MM/YYYY
        r'\b(\d{2,4})[/-](\d{1,2})[/-](\d{1,2})\b',  # YYYY/MM/DD
        r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{2,4})\b'  # DD Mon YYYY
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                # Simple date parsing - can be enhanced
                groups = match.groups()
                if len(groups) == 3:
                    # Try to parse as date
                    day, month, year = groups
                    if len(year) == 2:
                        year = "20" + year
                    
                    # Basic validation
                    if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            except (ValueError, IndexError):
                continue
    
    return ""

def validate_receipt_structure(data: Dict[str, Any]) -> List[str]:
    """Validate the structure and content of receipt data"""
    issues = []
    
    required_fields = ["amount", "account_number"]
    for field in required_fields:
        if field not in data or not data[field]:
            issues.append(f"Missing required field: {field}")
    
    # Validate amount is reasonable
    if "amount" in data:
        try:
            amount = float(data["amount"])
            if amount <= 0:
                issues.append("Amount must be greater than zero")
            if amount > 10000:  # Arbitrary large amount check
                issues.append("Amount seems unusually large")
        except (ValueError, TypeError):
            issues.append("Amount is not a valid number")
    
    return issues

def is_business_hours_transaction(date_str: str) -> bool:
    """Check if transaction was made during business hours (basic validation)"""
    try:
        # This is a simple check - can be enhanced based on needs
        date_obj = datetime.fromisoformat(date_str)
        hour = date_obj.hour
        weekday = date_obj.weekday()
        
        # Business hours: 8 AM to 6 PM, Monday to Friday
        return 8 <= hour <= 18 and weekday < 5
    except:
        return True  # Assume valid if can't parse
