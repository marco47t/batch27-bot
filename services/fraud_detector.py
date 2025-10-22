"""
Enhanced fraud detection with receipt age analysis and improved duplicate scoring
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
    Calculate consolidated fraud score with receipt age detection
    
    SCORING SYSTEM (max 100 points):
    - Duplicate Detection: 50 points (image similarity)
    - Transaction ID Duplicate: 25 points
    - Gemini AI Analysis: 40 points
    - Image Forensics: 30 points
    - Old Receipt Penalty: up to 20 points
    
    Returns:
        dict with fraud_score (0-100), risk_level, and recommendation
    """
    
    fraud_indicators = []
    fraud_score = 0
    max_score = 100
    
    # === DUPLICATE DETECTION (50 points MAX) ===
    # This is the MOST reliable indicator of fraud
    if duplicate_check_result.get("is_duplicate"):
        similarity = duplicate_check_result.get("similarity_score", 0)
        
        # Scale score based on similarity percentage
        if similarity >= 95:
            duplicate_points = 50  # Near-exact match = VERY HIGH RISK
        elif similarity >= 90:
            duplicate_points = 45  # 90-95% = HIGH RISK (should trigger rejection)
        elif similarity >= 85:
            duplicate_points = 35  # 85-90% = Manual review
        elif similarity >= 75:
            duplicate_points = 25  # 75-85% = Manual review
        else:
            duplicate_points = 15  # <75% = Low concern
        
        fraud_score += duplicate_points
        fraud_indicators.append(f"Duplicate receipt detected (similarity: {similarity:.1f}%)")
        logger.warning(f"Duplicate detected: +{duplicate_points} points (similarity: {similarity:.1f}%)")
    
    # Transaction ID duplicate check (25 points)
    if duplicate_check_result.get("transaction_id_duplicate"):
        fraud_score += 25
        tx_id = duplicate_check_result.get('duplicate_transaction_id', 'Unknown')
        fraud_indicators.append(f"Transaction ID already used: {tx_id}")
        logger.warning(f"Transaction ID duplicate: +25 points (ID: {tx_id})")
    
    # === GEMINI AI ANALYSIS (40 points) ===
    gemini_authenticity = gemini_result.get("authenticity_score", 100)
    
    # Only penalize if authenticity is significantly low
    if gemini_authenticity < 70:
        gemini_fraud_contribution = ((100 - gemini_authenticity) / 100) * 40
        fraud_score += gemini_fraud_contribution
        fraud_indicators.append(f"Gemini authenticity low: {gemini_authenticity}%")
    
    # Tampering indicators (max 20 points)
    tampering = gemini_result.get("tampering_indicators", [])
    if tampering:
        # 5 points per indicator, max 20 points
        tampering_points = min(20, len(tampering) * 5)
        fraud_score += tampering_points
        for indicator in tampering[:3]:  # Show first 3
            fraud_indicators.append(f"Tampering: {indicator}")
    
    # Old receipt penalty (max 20 points)
    days_since_transfer = gemini_result.get("days_since_transfer")
    if days_since_transfer and days_since_transfer > 7:  # Threshold: 7 days
        # 2 points per day after 7 days (max 20 points)
        old_receipt_penalty = min(20, (days_since_transfer - 7) * 2)
        fraud_score += old_receipt_penalty
        fraud_indicators.append(f"Old receipt: {days_since_transfer} days since transfer")
        logger.warning(f"Old receipt: {days_since_transfer} days old, penalty: +{old_receipt_penalty}")
    
    # === IMAGE FORENSICS (30 points MAX) ===
    # High confidence forgery detection
    if image_forensics_result.get("is_forged"):
        fraud_score += 30
        fraud_indicators.append("Image forensics: Possible forgery detected")
    
    # ELA analysis (max 20 points)
    ela_score = image_forensics_result.get("ela_score", 0)
    if ela_score > 50:
        ela_contribution = min(20, (ela_score / 100) * 20)
        fraud_score += ela_contribution
        fraud_indicators.append(f"ELA anomaly score: {ela_score}%")
    
    # Cap fraud score at 100
    fraud_score = min(100, fraud_score)
    
    # Determine risk level and recommendation
    if fraud_score >= 70:
        risk_level = "HIGH"
        recommendation = "REJECT"
    elif fraud_score >= 40:
        risk_level = "MEDIUM"
        recommendation = "MANUAL_REVIEW"
    else:
        risk_level = "LOW"
        recommendation = "ACCEPT"
    
    logger.info(f"Consolidated fraud score: {fraud_score}/100 (Risk: {risk_level})")
    
    return {
        "fraud_score": round(fraud_score, 2),
        "risk_level": risk_level,
        "fraud_indicators": fraud_indicators,
        "recommendation": recommendation
    }
