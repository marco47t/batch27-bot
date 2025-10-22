"""
Enhanced fraud detection with screenshot-aware scoring
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

logger = logging.getLogger(__name__)

def calculate_consolidated_fraud_score(
    gemini_result: Dict[str, Any],
    image_forensics_result: Dict[str, Any],
    duplicate_check_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculate consolidated fraud score with screenshot-aware adjustments
    
    SCORING SYSTEM (max 100 points):
    - Duplicate Detection: 40 points (HIGHEST - most reliable)
    - Gemini AI Analysis: 35 points (AI validation)
    - Image Forensics: 25 points (REDUCED - can false-positive on screenshots)
    """
    fraud_indicators = []
    fraud_score = 0
    
    is_screenshot = image_forensics_result.get("screenshot_flag", True)
    
    # === DUPLICATE DETECTION (40 points) - HIGHEST PRIORITY ===
    if duplicate_check_result.get("is_duplicate"):
        similarity = duplicate_check_result.get("similarity_percentage", 0)
        
        # Scale score based on similarity
        if similarity >= 95:
            duplicate_points = 40
        elif similarity >= 85:
            duplicate_points = 30
        elif similarity >= 75:
            duplicate_points = 20
        else:
            duplicate_points = 10
        
        fraud_score += duplicate_points
        fraud_indicators.append(f"Duplicate receipt detected (similarity: {similarity:.1f}%)")
    
    # Transaction ID duplicate check
    if duplicate_check_result.get("transaction_id_duplicate"):
        fraud_score += 25
        fraud_indicators.append(f"Transaction ID already used: {duplicate_check_result.get('duplicate_transaction_id')}")
    
    # === GEMINI AI ANALYSIS (35 points) ===
    gemini_authenticity = gemini_result.get("authenticity_score", 100)
    
    # Only penalize if authenticity is significantly low
    if gemini_authenticity < 70:
        gemini_fraud_contribution = ((100 - gemini_authenticity) / 100) * 35
        fraud_score += gemini_fraud_contribution
        fraud_indicators.append(f"Gemini authenticity low: {gemini_authenticity}%")
    
    # Tampering indicators (max 15 points)
    tampering = gemini_result.get("tampering_indicators", [])
    if tampering:
        tampering_points = min(15, len(tampering) * 5)
        fraud_score += tampering_points
        for indicator in tampering:
            fraud_indicators.append(f"Tampering: {indicator}")
    
    # Old receipt penalty (max 15 points)
    days_since_transfer = gemini_result.get("days_since_transfer")
    if days_since_transfer and days_since_transfer > 7:  # Increased threshold from 5 to 7 days
        # 2 points per day after 7 days (max 15 points)
        old_receipt_penalty = min(15, (days_since_transfer - 7) * 2)
        fraud_score += old_receipt_penalty
        fraud_indicators.append(f"Old receipt: {days_since_transfer} days since transfer")
        logger.warning(f"Old receipt detected: {days_since_transfer} days old, penalty: +{old_receipt_penalty}")
    
    # === IMAGE FORENSICS (25 points MAX) - REDUCED FOR SCREENSHOTS ===
    forensics_score = 0
    
    # High confidence forgery detection
    if image_forensics_result.get("is_forged"):
        forensics_score += 25
        fraud_indicators.append("Image forensics: Possible forgery detected")
    else:
        # ELA analysis - HEAVILY REDUCED for screenshots
        ela_data = image_forensics_result.get("ela_check", {})
        ela_risk = ela_data.get("risk_level", "LOW")
        ela_score_value = ela_data.get("risk_score", 0)
        
        if is_screenshot:
            # Screenshots: Only flag if ELA is HIGH risk
            if ela_risk == "HIGH" and ela_score_value >= 5:
                forensics_score += 10  # Max 10 points for screenshot ELA
                fraud_indicators.append(f"ELA anomaly (screenshot-adjusted)")
        else:
            # Regular photos: More sensitive
            if ela_risk == "HIGH":
                forensics_score += 20
                fraud_indicators.append(f"ELA anomaly score: HIGH")
            elif ela_risk == "MEDIUM":
                forensics_score += 10
                fraud_indicators.append(f"ELA anomaly score: MEDIUM")
    
    fraud_score += forensics_score
    
    # Cap fraud score at 100
    fraud_score = min(100, fraud_score)
    
    # Determine risk level and recommendation
    if fraud_score >= 70:
        risk_level = "HIGH"
        recommendation = "REJECT"
    elif fraud_score >= 45:  # Increased threshold from 40 to 45
        risk_level = "MEDIUM"
        recommendation = "MANUAL_REVIEW"
    else:
        risk_level = "LOW"
        recommendation = "ACCEPT"
    
    logger.info(f"Consolidated fraud score: {fraud_score}/100 (Risk: {risk_level})")
    if is_screenshot:
        logger.info("Screenshot detected - forensics scoring adjusted")
    
    return {
        "fraud_score": round(fraud_score, 2),
        "risk_level": risk_level,
        "fraud_indicators": fraud_indicators,
        "recommendation": recommendation,
        "is_screenshot": is_screenshot
    }
