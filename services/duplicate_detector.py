# services/duplicate_detector.py
import hashlib
import cv2
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
import logging
from database import get_db, crud
import imagehash
from PIL import Image
import os
import tempfile

logger = logging.getLogger(__name__)


def compute_multi_hash(image_path: str) -> Dict[str, str]:
    """
    Compute multiple perceptual hashes for better duplicate detection
    Returns dict with different hash types
    """
    temp_file = None
    try:
        # If S3 URL, download first
        if image_path.startswith('http'):
            from utils.s3_storage import download_receipt_from_s3
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                temp_file = tmp.name
            download_receipt_from_s3(image_path, temp_file)
            image_path = temp_file
        
        # Load image with PIL for imagehash library
        img_pil = Image.open(image_path)
        
        # Compute multiple hash types (more resistant to edits)
        hashes = {
            'phash': str(imagehash.phash(img_pil, hash_size=16)),      # Perceptual hash (16x16 = 256 bits)
            'dhash': str(imagehash.dhash(img_pil, hash_size=16)),      # Difference hash
            'whash': str(imagehash.whash(img_pil, hash_size=16)),      # Wavelet hash
            'average': str(imagehash.average_hash(img_pil, hash_size=16))  # Average hash
        }
        
        # Also compute color histogram for content similarity
        img_cv = cv2.imread(image_path)
        if img_cv is not None:
            # Resize and compute histogram
            img_resized = cv2.resize(img_cv, (256, 256))
            hist = cv2.calcHist([img_resized], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            hashes['histogram'] = hashlib.sha256(hist.tobytes()).hexdigest()[:32]
        
        return hashes
    
    except Exception as e:
        logger.error(f"Multi-hash computation failed: {e}")
        return {}
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass


def compute_file_hash(image_path: str) -> str:
    """Compute exact file hash (supports S3 URLs)"""
    temp_file = None
    try:
        # If S3 URL, download first
        if image_path.startswith('http'):
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
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass


def calculate_similarity(hash1: Dict[str, str], hash2: Dict[str, str]) -> Tuple[float, str]:
    """
    Calculate similarity between two multi-hash sets
    Returns: (similarity_percentage, match_type)
    """
    if not hash1 or not hash2:
        return 0.0, "UNKNOWN"
    
    similarities = []
    
    # Compare each hash type
    for hash_type in ['phash', 'dhash', 'whash', 'average']:
        if hash_type in hash1 and hash_type in hash2:
            h1 = imagehash.hex_to_hash(hash1[hash_type])
            h2 = imagehash.hex_to_hash(hash2[hash_type])
            # Calculate similarity (lower hamming distance = more similar)
            hamming_dist = h1 - h2
            max_bits = 256  # 16x16 hash
            similarity = ((max_bits - hamming_dist) / max_bits) * 100
            similarities.append(similarity)
    
    if not similarities:
        return 0.0, "UNKNOWN"
    
    # Use average similarity across all hash types
    avg_similarity = sum(similarities) / len(similarities)
    
    # Determine match type based on similarity
    if avg_similarity >= 98:
        return avg_similarity, "EXACT"
    elif avg_similarity >= 85:
        return avg_similarity, "VERY_SIMILAR"
    elif avg_similarity >= 75:
        return avg_similarity, "SIMILAR"
    else:
        return avg_similarity, "DIFFERENT"


def check_duplicate_submission(user_id: int, image_path: str, similarity_threshold: float = 75.0, previous_receipt_paths: list = None) -> Dict[str, Any]:
    """
    Enhanced duplicate detection using multiple perceptual hashing algorithms
    Now supports checking against specific previous receipt paths (for partial payments)
    
    Args:
        user_id: Current user ID
        image_path: Path or URL to receipt image
        similarity_threshold: Minimum similarity % to flag as duplicate (default: 75%)
        previous_receipt_paths: Optional list of specific receipt paths to check against (for same user's partial payments)
    
    Returns dict with duplicate detection results
    """
    try:
        # Compute exact file hash
        file_hash = compute_file_hash(image_path)
        
        # Compute multiple perceptual hashes
        multi_hash = compute_multi_hash(image_path)
        
        if not multi_hash:
            return {
                'is_duplicate': False,
                'risk_level': 'UNKNOWN',
                'message': 'Could not compute image signature'
            }
        
        with get_db() as session:
            from database.models import Transaction, Enrollment, User
            
            # ✅ FIRST: Check against provided previous receipts (for same user's partial payments)
            if previous_receipt_paths:
                logger.info(f"Checking against {len(previous_receipt_paths)} previous receipts from same user")
                
                for prev_path in previous_receipt_paths:
                    if not prev_path:
                        continue
                    
                    # Check exact duplicate (file hash)
                    prev_file_hash = compute_file_hash(prev_path)
                    if prev_file_hash and prev_file_hash == file_hash:
                        return {
                            'is_duplicate': True,
                            'risk_level': 'HIGH',
                            'match_type': 'EXACT',
                            'similarity_percentage': 100.0,
                            'original_receipt_path': prev_path,
                            'message': '⚠️ You already submitted this exact receipt before. Please submit a NEW receipt for the remaining amount.'
                        }
                    
                    # Check perceptual similarity
                    prev_multi_hash = compute_multi_hash(prev_path)
                    if prev_multi_hash:
                        similarity, match_type = calculate_similarity(multi_hash, prev_multi_hash)
                        
                        if similarity >= similarity_threshold:
                            return {
                                'is_duplicate': True,
                                'risk_level': 'HIGH' if similarity >= 90 else 'MEDIUM',
                                'match_type': match_type,
                                'similarity_percentage': similarity,
                                'original_receipt_path': prev_path,
                                'message': f'⚠️ This receipt is {similarity:.1f}% similar to one you already submitted. Please submit a NEW receipt.'
                            }
            
            # THEN: Check ALL transactions from ALL users (cross-user duplicate check)
            all_transactions = session.query(Transaction).join(
                Enrollment, Transaction.enrollment_id == Enrollment.enrollment_id
            ).join(
                User, Enrollment.user_id == User.user_id
            ).all()
            
            best_match = None
            best_similarity = 0.0
            
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
                        'message': 'Exact duplicate - identical file submitted before by another user'
                    }
                
                # Check perceptual similarity with multiple algorithms
                prev_multi_hash = compute_multi_hash(txn.receipt_image_path)
                if prev_multi_hash:
                    similarity, match_type = calculate_similarity(multi_hash, prev_multi_hash)
                    
                    # Keep track of best match
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = {
                            'is_duplicate': similarity >= similarity_threshold,
                            'risk_level': 'HIGH' if similarity >= 90 else 'MEDIUM' if similarity >= 80 else 'LOW',
                            'match_type': match_type,
                            'similarity_percentage': similarity,
                            'matched_transaction_id': txn.transaction_id,
                            'original_user_id': original_user.user_id,
                            'original_user_name': f"{original_user.first_name or ''} {original_user.last_name or ''}".strip() or "Unknown",
                            'original_user_username': original_user.username or "N/A",
                            'original_telegram_id': original_user.telegram_user_id,
                            'original_receipt_path': txn.receipt_image_path,
                            'message': f'Duplicate detected ({similarity:.1f}% similar) - receipt already used by another user'
                        }
            
            # Return best match if above threshold
            if best_match and best_match['is_duplicate']:
                return best_match
            
            return {
                'is_duplicate': False,
                'risk_level': 'LOW',
                'message': 'No duplicates found',
                'best_similarity': best_similarity
            }
    
    except Exception as e:
        logger.error(f"Duplicate check failed: {e}")
        return {
            'is_duplicate': False,
            'risk_level': 'UNKNOWN',
            'message': f'Duplicate check error: {str(e)}'
        }
