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
            'phash': str(imagehash.phash(img_pil, hash_size=16)),  # Perceptual hash (16x16 = 256 bits)
            'dhash': str(imagehash.dhash(img_pil, hash_size=16)),  # Difference hash
            'whash': str(imagehash.whash(img_pil, hash_size=16)),  # Wavelet hash
        }
        
        return hashes
    except Exception as e:
        logger.error(f"Failed to compute hash for {image_path}: {e}")
        return None
    finally:
        # Clean up temp file if created
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass


def compute_file_hash(image_path: str) -> Optional[str]:
    """Compute exact file hash (SHA256) for exact duplicate detection"""
    temp_file = None
    try:
        # Download if S3 URL
        if image_path.startswith('http'):
            from utils.s3_storage import download_receipt_from_s3
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                temp_file = tmp.name
            download_receipt_from_s3(image_path, temp_file)
            image_path = temp_file
        
        with open(image_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.error(f"Failed to compute file hash: {e}")
        return None
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass


def calculate_similarity(hash1: Dict[str, str], hash2: Dict[str, str]) -> Tuple[float, str]:
    """
    Calculate similarity between two multi-hash dictionaries
    Returns (similarity_percentage, match_type)
    """
    try:
        # Calculate similarity for each hash type
        similarities = {}
        
        for hash_type in ['phash', 'dhash', 'whash']:
            if hash_type in hash1 and hash_type in hash2:
                h1 = imagehash.hex_to_hash(hash1[hash_type])
                h2 = imagehash.hex_to_hash(hash2[hash_type])
                
                # Calculate hamming distance (lower = more similar)
                distance = h1 - h2
                max_distance = len(hash1[hash_type]) * 4  # 4 bits per hex char
                
                # Convert to similarity percentage
                similarity = max(0, (1 - distance / max_distance) * 100)
                similarities[hash_type] = similarity
        
        if not similarities:
            return 0.0, 'NONE'
        
        # Use the MAXIMUM similarity (most optimistic)
        max_similarity = max(similarities.values())
        
        # Determine match type
        if max_similarity >= 95:
            match_type = 'EXACT'
        elif max_similarity >= 85:
            match_type = 'VERY_HIGH'
        elif max_similarity >= 75:
            match_type = 'HIGH'
        elif max_similarity >= 60:
            match_type = 'MEDIUM'
        else:
            match_type = 'LOW'
        
        return max_similarity, match_type
        
    except Exception as e:
        logger.error(f"Similarity calculation failed: {e}")
        return 0.0, 'ERROR'


def check_duplicate_submission(user_id: int, image_path: str, similarity_threshold: float = 75.0, previous_receipt_paths: list = None) -> Dict[str, Any]:
    """
    Enhanced duplicate detection - checks ALL enrollments in database
    Supports comma-separated receipt paths
    """
    try:
        logger.info(f"🔍 Starting duplicate detection for user {user_id}")
        
        # Compute exact file hash
        file_hash = compute_file_hash(image_path)
        logger.info(f"📄 Computed file hash for new receipt: {file_hash[:16]}...")
        
        # Compute multiple perceptual hashes
        multi_hash = compute_multi_hash(image_path)
        
        if not multi_hash:
            return {
                'is_duplicate': False,
                'risk_level': 'UNKNOWN',
                'message': 'Could not compute image signature'
            }
        
        logger.info(f"🔑 Computed perceptual hashes: phash={multi_hash['phash'][:16]}...")
        
        with get_db() as session:
            from database.models import Enrollment, User
            
            # ✅ FIRST: Check against same user's previous receipts
            if previous_receipt_paths:
                expanded_paths = []
                for path in previous_receipt_paths:
                    if path:
                        expanded_paths.extend([p.strip() for p in path.split(',') if p.strip()])
                
                logger.info(f"Checking against {len(expanded_paths)} previous receipts from SAME user")
                
                for idx, prev_path in enumerate(expanded_paths):
                    logger.info(f"  → Checking same-user receipt {idx+1}/{len(expanded_paths)}: {prev_path[-50:]}")
                    
                    # Check exact duplicate
                    prev_file_hash = compute_file_hash(prev_path)
                    if prev_file_hash and prev_file_hash == file_hash:
                        logger.warning(f"🚨 EXACT MATCH with own previous receipt!")
                        return {
                            'is_duplicate': True,
                            'risk_level': 'HIGH',
                            'match_type': 'EXACT',
                            'similarity_percentage': 100.0,
                            'original_receipt_path': prev_path,
                            'message': '⚠️ You already submitted this exact receipt. Please submit a NEW receipt for the remaining amount.'
                        }
                    
                    # Check perceptual similarity
                    prev_multi_hash = compute_multi_hash(prev_path)
                    if prev_multi_hash:
                        similarity, match_type = calculate_similarity(multi_hash, prev_multi_hash)
                        logger.info(f"    Similarity: {similarity:.1f}% ({match_type})")
                        
                        if similarity >= similarity_threshold:
                            logger.warning(f"⚠️ HIGH SIMILARITY with own previous receipt: {similarity:.1f}%")
                            return {
                                'is_duplicate': True,
                                'risk_level': 'HIGH' if similarity >= 90 else 'MEDIUM',
                                'match_type': match_type,
                                'similarity_percentage': similarity,
                                'original_receipt_path': prev_path,
                                'message': f'⚠️ This receipt is {similarity:.1f}% similar to one you already submitted.'
                            }
            
            # ✅ SECOND: Check ALL enrollments in database (cross-user check)
            all_enrollments = session.query(Enrollment).join(User).all()
            
            logger.info(f"🔍 Checking duplicate against {len(all_enrollments)} total enrollments in database")
            
            best_match = None
            best_similarity = 0.0
            total_receipts_checked = 0
            
            for enrollment in all_enrollments:
                if not enrollment.receipt_image_path:
                    continue
                
                # ✅ Split comma-separated receipt paths
                receipt_paths = [p.strip() for p in enrollment.receipt_image_path.split(',') if p.strip()]
                
                for receipt_path in receipt_paths:
                    total_receipts_checked += 1
                    
                    # ✅ Check BOTH same user AND other users' receipts
                    original_user = enrollment.user
                    is_same_user = enrollment.user_id == user_id
                    
                    logger.info(f"  → Checking receipt {total_receipts_checked}: Enrollment #{enrollment.enrollment_id}, User {original_user.telegram_user_id} {'(SAME USER)' if is_same_user else '(OTHER USER)'}")
                    
                    # Check exact duplicate
                    prev_file_hash = compute_file_hash(receipt_path)
                    if prev_file_hash and prev_file_hash == file_hash:
                        if is_same_user:
                            logger.warning(f"🚨 EXACT DUPLICATE with own enrollment {enrollment.enrollment_id}")
                            return {
                                'is_duplicate': True,
                                'risk_level': 'HIGH',
                                'match_type': 'EXACT',
                                'similarity_percentage': 100.0,
                                'original_receipt_path': receipt_path,
                                'message': '⚠️ You already submitted this exact receipt for another enrollment.'
                            }
                        else:
                            logger.warning(f"🚨 EXACT DUPLICATE with OTHER user: Enrollment {enrollment.enrollment_id}, User {original_user.telegram_user_id}")
                            return {
                                'is_duplicate': True,
                                'risk_level': 'HIGH',
                                'match_type': 'EXACT',
                                'similarity_percentage': 100.0,
                                'matched_enrollment_id': enrollment.enrollment_id,
                                'original_user_id': original_user.user_id,
                                'original_user_name': f"{original_user.first_name or ''} {original_user.last_name or ''}".strip() or "Unknown",
                                'original_user_username': original_user.username or "N/A",
                                'original_telegram_id': original_user.telegram_user_id,
                                'original_receipt_path': receipt_path,
                                'message': 'Exact duplicate - identical receipt submitted by another user'
                            }
                    
                    # Check perceptual similarity
                    prev_multi_hash = compute_multi_hash(receipt_path)
                    if prev_multi_hash:
                        similarity, match_type = calculate_similarity(multi_hash, prev_multi_hash)
                        logger.info(f"    Similarity: {similarity:.1f}% ({match_type})")
                        
                        # Keep track of best match
                        if similarity > best_similarity:
                            best_similarity = similarity
                            best_match = {
                                'is_duplicate': similarity >= similarity_threshold,
                                'risk_level': 'HIGH' if similarity >= 90 else 'MEDIUM' if similarity >= 80 else 'LOW',
                                'match_type': match_type,
                                'similarity_percentage': similarity,
                                'matched_enrollment_id': enrollment.enrollment_id,
                                'original_user_id': original_user.user_id,
                                'original_user_name': f"{original_user.first_name or ''} {original_user.last_name or ''}".strip() or "Unknown",
                                'original_user_username': original_user.username or "N/A",
                                'original_telegram_id': original_user.telegram_user_id,
                                'original_receipt_path': receipt_path,
                                'message': f'Duplicate detected ({similarity:.1f}% similar) - receipt used by {"same user" if is_same_user else "another user"}'
                            }
            
            logger.info(f"✅ Duplicate check complete: {total_receipts_checked} receipts checked from {len(all_enrollments)} enrollments")
            logger.info(f"📊 Best match: {best_similarity:.1f}% similarity")
            
            # Return best match if above threshold
            if best_match and best_match['is_duplicate']:
                logger.warning(f"⚠️ SIMILAR DUPLICATE: {best_match['similarity_percentage']:.1f}% match")
                return best_match
            
            return {
                'is_duplicate': False,
                'risk_level': 'LOW',
                'message': 'No duplicates found',
                'best_similarity': best_similarity
            }
    
    except Exception as e:
        logger.error(f"Duplicate check failed: {e}", exc_info=True)
        return {
            'is_duplicate': False,
            'risk_level': 'UNKNOWN',
            'message': f'Duplicate check error: {str(e)}'
        }
