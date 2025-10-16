# services/duplicate_detector.py
import hashlib
import cv2
import numpy as np
from typing import Dict, Any, List
import logging
from database import get_db, crud

logger = logging.getLogger(__name__)

def compute_image_hash(image_path: str) -> str:
    """Compute perceptual hash that's resistant to minor edits"""
    try:
        # Read image
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        
        # Resize to standard size
        img_resized = cv2.resize(img, (64, 64))
        
        # Compute DCT
        dct = cv2.dct(np.float32(img_resized))
        
        # Keep only top-left 8x8 (low frequencies)
        dct_low = dct[:8, :8]
        
        # Compute median
        median = np.median(dct_low)
        
        # Create hash based on comparison to median
        hash_str = ""
        for i in range(8):
            for j in range(8):
                hash_str += '1' if dct_low[i, j] > median else '0'
        
        return hash_str
        
    except Exception as e:
        logger.error(f"Hash computation failed: {e}")
        return ""

def compute_file_hash(image_path: str) -> str:
    """Compute exact file hash"""
    try:
        with open(image_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.error(f"File hash failed: {e}")
        return ""

def hamming_distance(hash1: str, hash2: str) -> int:
    """Calculate hamming distance between two hashes"""
    if len(hash1) != len(hash2):
        return 999
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

def check_duplicate_submission(user_id: int, image_path: str, threshold: int = 5) -> Dict[str, Any]:
    """
    Check if this receipt is a duplicate or near-duplicate of previous submissions
    threshold: Maximum hamming distance to consider as duplicate (5 = ~8% difference)
    """
    try:
        # Compute hashes for new image
        file_hash = compute_file_hash(image_path)
        perceptual_hash = compute_image_hash(image_path)
        
        if not perceptual_hash:
            return {
                'is_duplicate': False,
                'risk_level': 'UNKNOWN',
                'message': 'Could not compute image signature'
            }
        
        # Query database for user's previous transactions
        with get_db() as session:
            from database.models import Transaction, Enrollment
            
            # FIXED: Join Transaction with Enrollment to filter by user_id
            previous_transactions = session.query(Transaction).join(
                Enrollment, Transaction.enrollment_id == Enrollment.enrollment_id
            ).filter(
                Enrollment.user_id == user_id  # Now we can access user_id through Enrollment
            ).all()

            
            for txn in previous_transactions:
                if not txn.receipt_image_path:
                    continue
                
                # Check exact duplicate (file hash)
                prev_file_hash = compute_file_hash(txn.receipt_image_path)
                if prev_file_hash == file_hash:
                    return {
                        'is_duplicate': True,
                        'risk_level': 'HIGH',
                        'match_type': 'EXACT',
                        'matched_transaction_id': txn.transaction_id,
                        'message': 'Exact duplicate - same file submitted before'
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
                            'message': f'Near-duplicate detected ({similarity_pct:.1f}% similar) - possible edited receipt'
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
