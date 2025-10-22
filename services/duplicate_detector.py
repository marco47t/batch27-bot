# services/duplicate_detector.py
import hashlib
import cv2
import numpy as np
from typing import Dict, Any, Optional
import logging
from database import get_db, crud

logger = logging.getLogger(__name__)


def compute_image_hash(image_path: str) -> str:
    """Compute perceptual hash that's resistant to minor edits"""
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        img_resized = cv2.resize(img, (64, 64))
        dct = cv2.dct(np.float32(img_resized))
        dct_low = dct[:8, :8]
        median = np.median(dct_low)
        
        hash_str = ""
        for i in range(8):
            for j in range(8):
                hash_str += '1' if dct_low[i, j] > median else '0'
        return hash_str
    except Exception as e:
        logger.error(f"Hash computation failed: {e}")
        return ""


def compute_file_hash(image_path: str) -> str:
    """Compute exact file hash (supports S3 URLs)"""
    temp_file = None
    try:
        # If S3 URL, download first
        if image_path.startswith('http'):
            import tempfile
            import os
            from utils.s3_storage import download_receipt_from_s3
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                temp_file = tmp.name
            download_receipt_from_s3(image_path, temp_file)
            image_path = temp_file
        
        with open(image_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.error(f"File hash failed: {e}")
        return ""
    finally:
        # Clean up temp file
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass



def hamming_distance(hash1: str, hash2: str) -> int:
    """Calculate hamming distance between two hashes"""
    if len(hash1) != len(hash2):
        return 999
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


def check_duplicate_submission(user_id: int, image_path: str, threshold: int = 5) -> Dict[str, Any]:
    """
    Check if this receipt is a duplicate across ALL users (not just current user)
    
    Returns dict with:
        - is_duplicate: bool
        - risk_level: str
        - match_type: str (EXACT or SIMILAR)
        - similarity_percentage: float
        - matched_transaction_id: int
        - original_user_id: int
        - original_user_name: str
        - original_user_username: str
        - original_telegram_id: int
        - original_receipt_path: str
        - message: str
    """
    try:
        file_hash = compute_file_hash(image_path)
        perceptual_hash = compute_image_hash(image_path)
        
        if not perceptual_hash:
            return {
                'is_duplicate': False,
                'risk_level': 'UNKNOWN',
                'message': 'Could not compute image signature'
            }
        
        with get_db() as session:
            from database.models import Transaction, Enrollment, User
            
            # Query ALL transactions from ALL users
            all_transactions = session.query(Transaction).join(
                Enrollment, Transaction.enrollment_id == Enrollment.enrollment_id
            ).join(
                User, Enrollment.user_id == User.user_id
            ).all()
            
            for txn in all_transactions:
                if not txn.receipt_image_path:
                    continue
                
                # Skip if this is current user's own transaction
                if txn.enrollment.user_id == user_id:
                    continue
                
                original_user = txn.enrollment.user
                
                # Check exact duplicate (file hash)
                prev_file_hash = compute_file_hash(txn.receipt_image_path)
                if prev_file_hash and prev_file_hash == file_hash:
                    return {
                        'is_duplicate': True,
                        'risk_level': 'HIGH',
                        'match_type': 'EXACT',
                        'similarity_percentage': 100.0,
                        'matched_transaction_id': txn.transaction_id,
                        'original_user_id': original_user.user_id,
                        'original_user_name': f"{original_user.first_name or ''} {original_user.last_name or ''}".strip() or "Unknown",
                        'original_user_username': original_user.username or "N/A",
                        'original_telegram_id': original_user.telegram_user_id,
                        'original_receipt_path': txn.receipt_image_path,
                        'message': 'Exact duplicate - same file submitted before by another user'
                    }
                
                # Check visual similarity (perceptual hash)
                prev_perceptual_hash = compute_image_hash(txn.receipt_image_path)
                if prev_perceptual_hash:
                    distance = hamming_distance(perceptual_hash, prev_perceptual_hash)
                    
                    if distance <= threshold:
                        similarity_pct = ((64 - distance) / 64) * 100
                        return {
                            'is_duplicate': True,
                            'risk_level': 'HIGH',
                            'match_type': 'SIMILAR',
                            'similarity_percentage': similarity_pct,
                            'matched_transaction_id': txn.transaction_id,
                            'original_user_id': original_user.user_id,
                            'original_user_name': f"{original_user.first_name or ''} {original_user.last_name or ''}".strip() or "Unknown",
                            'original_user_username': original_user.username or "N/A",
                            'original_telegram_id': original_user.telegram_user_id,
                            'original_receipt_path': txn.receipt_image_path,
                            'message': f'Near-duplicate detected ({similarity_pct:.1f}% similar) - receipt already used by another user'
                        }
            
            return {
                'is_duplicate': False,
                'risk_level': 'LOW',
                'message': 'No duplicates found'
            }
    
    except Exception as e:
        logger.error(f"Duplicate check failed: {e}")
        return {
            'is_duplicate': False,
            'risk_level': 'UNKNOWN',
            'message': f'Duplicate check error: {str(e)}'
        }
