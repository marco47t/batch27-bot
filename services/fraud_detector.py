"""
Enhanced fraud detection with receipt age analysis
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
    
    Returns:
        dict with fraud_score (0-100) and risk_level
    """
    fraud_indicators = []
    fraud_score = 0
    max_score = 100
    
    # === GEMINI AI ANALYSIS (40 points) ===
    gemini_authenticity = gemini_result.get("authenticity_score", 100)
    gemini_fraud_contribution = max(0, (100 - gemini_authenticity) * 0.4)
    fraud_score += gemini_fraud_contribution
    
    if gemini_authenticity < 60:
        fraud_indicators.append(f"Gemini authenticity low: {gemini_authenticity}%")
    
    # Tampering indicators
    tampering = gemini_result.get("tampering_indicators", [])
    if tampering:
        fraud_score += len(tampering) * 5  # 5 points per indicator
        for indicator in tampering:
            fraud_indicators.append(f"Tampering: {indicator}")
    
    # ✅ Old receipt penalty (days since transfer)
    days_since_transfer = gemini_result.get("days_since_transfer")
    if days_since_transfer and days_since_transfer > 5:
        # Add 2 points per day after 5 days (max 20 points)
        old_receipt_penalty = min(20, (days_since_transfer - 5) * 2)
        fraud_score += old_receipt_penalty
        fraud_indicators.append(f"Old receipt: {days_since_transfer} days since transfer (penalty: +{old_receipt_penalty} points)")
        logger.warning(f"Old receipt detected: {days_since_transfer} days old, penalty: +{old_receipt_penalty}")
    
    # === IMAGE FORENSICS (30 points) ===
    if image_forensics_result.get("is_forged"):
        fraud_score += 30
        fraud_indicators.append("Image forensics: Possible forgery detected")
    
    # ELA analysis
    ela_score = image_forensics_result.get("ela_score", 0)
    if ela_score > 50:
        ela_contribution = (ela_score / 100) * 15
        fraud_score += ela_contribution
        fraud_indicators.append(f"ELA anomaly score: {ela_score}%")
    
    # === TRANSACTION ID DUPLICATE (50 points - HIGH PRIORITY) ===
    # ✅ INCREASED: Transaction ID duplicate now worth 50 points (was 25)
    if duplicate_check_result.get("transaction_id_duplicate"):
        fraud_score += 50
        duplicate_tx_id = duplicate_check_result.get('duplicate_transaction_id', 'Unknown')
        fraud_indicators.append(f"Transaction ID already used: {duplicate_tx_id}")
        logger.warning(f"Transaction ID duplicate: +50 points (ID: {duplicate_tx_id})")
    
    # ❌ REMOVED: Image duplicate checking (was 30 points)
    # Image comparison is too slow and unreliable - transaction ID is sufficient
    
    # Cap fraud score at 100
    fraud_score = min(100, fraud_score)
    
    # Determine risk level
    if fraud_score >= 70:
        risk_level = "HIGH"
    elif fraud_score >= 40:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"
    
    logger.info(f"Consolidated fraud score: {fraud_score}/100 (Risk: {risk_level})")
    
    return {
        "fraud_score": round(fraud_score, 2),
        "risk_level": risk_level,
        "fraud_indicators": fraud_indicators,
        "recommendation": "REJECT" if fraud_score >= 70 else "MANUAL_REVIEW" if fraud_score >= 40 else "ACCEPT"
    }
