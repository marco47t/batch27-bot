# services/fraud_detector.py

from typing import Dict, Any
import logging
from .image_forensics import analyze_image_metadata
from .ela_detector import perform_ela
from .duplicate_detector import check_duplicate_submission

logger = logging.getLogger(__name__)

def calculate_consolidated_fraud_score(
    user_id: int,
    image_path: str,
    gemini_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Combine multiple fraud detection signals into consolidated score
    Score: 0-100 where 100 = highest fraud risk
    
    IMPORTANT: Screenshots are NORMAL and NOT penalized
    """
    
    fraud_score = 0
    fraud_indicators = []
    checks_performed = []
    
    # 1. EXIF Metadata Analysis (Weight: 20 points max)
    # SCREENSHOTS ARE NORMAL - NO PENALTY
    logger.info(f"Running metadata analysis for user {user_id}")
    metadata_result = analyze_image_metadata(image_path)
    checks_performed.append("metadata_analysis")
    
    if metadata_result.get("screenshot_flag"):
        # Screenshot is NORMAL - just note it, no penalty
        fraud_indicators.append("Receipt is a screenshot (normal for users)")
        logger.info(f"User {user_id} submitted screenshot - this is expected")
    elif metadata_result["risk_level"] == "HIGH":
        fraud_score += 20
        fraud_indicators.append(f"Metadata: {metadata_result['reason']}")
    elif metadata_result["risk_level"] == "MEDIUM":
        fraud_score += 10
        fraud_indicators.append(f"Metadata warning: {metadata_result['reason']}")
    
    # 2. Error Level Analysis (Weight: 25 points max)
    # More lenient for screenshots
    logger.info(f"Running ELA for user {user_id}")
    ela_result = perform_ela(image_path)
    checks_performed.append("error_level_analysis")
    
    if ela_result["risk_level"] == "HIGH":
        fraud_score += 25
        fraud_indicators.append(f"Image tampering detected: {ela_result['message']}")
    elif ela_result["risk_level"] == "MEDIUM":
        fraud_score += 10  # Reduced from 12 for screenshot tolerance
        fraud_indicators.append(f"Possible tampering: {ela_result['message']}")
    
    # 3. Duplicate Detection (Weight: 30 points)
    logger.info(f"Running duplicate check for user {user_id}")
    duplicate_result = check_duplicate_submission(user_id, image_path)
    checks_performed.append("duplicate_detection")
    
    if duplicate_result["is_duplicate"]:
        fraud_score += 30
        fraud_indicators.append(f"Duplicate: {duplicate_result['message']}")
    
    # 4. Gemini AI Analysis (Weight: 25 points)
    checks_performed.append("ai_validation")
    
    if not gemini_result.get("is_valid", False):
        fraud_score += 15
        fraud_indicators.append(f"AI validation failed: {gemini_result.get('reason', 'Unknown')}")
    
    # Check for tampering indicators from Gemini
    tampering_indicators = gemini_result.get("tampering_indicators", [])
    if tampering_indicators:
        fraud_score += min(len(tampering_indicators) * 3, 10)
        for indicator in tampering_indicators[:2]:  # Add top 2
            fraud_indicators.append(f"AI detected: {indicator}")
    
    # Check authenticity score from Gemini
    authenticity_score = gemini_result.get("authenticity_score", 100)
    if authenticity_score < 70:
        fraud_score += 10
        fraud_indicators.append(f"Low authenticity score: {authenticity_score}/100")
    
    # Determine risk level and action
    if fraud_score >= 40:
        risk_level = "HIGH"
        action = "REJECT"
    elif fraud_score >= 20:
        risk_level = "MEDIUM"
        action = "MANUAL_REVIEW"
    else:
        risk_level = "LOW"
        action = "APPROVE"
    
    return {
        "fraud_score": min(fraud_score, 100),
        "risk_level": risk_level,
        "action": action,
        "fraud_indicators": fraud_indicators,
        "checks_performed": checks_performed,
        "metadata_check": metadata_result,
        "ela_check": ela_result,
        "duplicate_check": duplicate_result,
        "ai_validation": gemini_result
    }
