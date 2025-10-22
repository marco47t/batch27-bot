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
    IMAGE DUPLICATE CHECK - DISABLED (Always returns 0 score)
    Kept for compatibility but returns no fraud risk
    """
    try:
        logger.info(f"🔍 Image duplicate check: DISABLED (returns 0 score)")
        
        # Return immediately with 0 score
        return {
            'is_duplicate': False,
            'risk_level': 'LOW',
            'match_type': 'NONE',
            'similarity_score': 0,
            'image_similarity_score': 0,
            'best_similarity': 0,
            'message': 'Image duplicate check disabled'
        }

        
    except Exception as e:
        logger.error(f"Duplicate check failed: {e}", exc_info=True)
        return {
            'is_duplicate': False,
            'risk_level': 'UNKNOWN',
            'message': f'Duplicate check error: {str(e)}',
            'image_similarity_score': 0
        }

def check_transaction_id_duplicate(transaction_id: str, user_id: int = None) -> Dict[str, Any]:
    """
    Check if transaction ID already exists in Transaction table
    Returns 50 fraud score if duplicate found
    """
    if not transaction_id:
        return {
            'is_duplicate': False,
            'fraud_score': 0,
            'message': 'No transaction ID provided'
        }
    
    try:
        with get_db() as session:
            from database.models import Transaction, Enrollment, User
            
            # Search for matching transaction ID
            existing_transaction = session.query(Transaction).filter(
                Transaction.receipt_transaction_id == transaction_id
            ).first()
            
            if existing_transaction:
                # Get enrollment and user info
                enrollment = session.query(Enrollment).filter(
                    Enrollment.enrollment_id == existing_transaction.enrollment_id
                ).first()
                
                original_user = enrollment.user if enrollment else None
                
                logger.warning(f"🚨 DUPLICATE TRANSACTION ID: {transaction_id}")
                
                return {
                    'is_duplicate': True,
                    'fraud_score': 50,  # Fixed score for ID duplicates
                    'risk_level': 'HIGH',
                    'match_type': 'TRANSACTION_ID',
                    'message': f'Transaction ID {transaction_id} already used',
                    'original_user_id': original_user.user_id if original_user else None,
                    'original_telegram_id': original_user.telegram_user_id if original_user else None,
                    'original_transaction_id': existing_transaction.transaction_id
                }
            
            return {
                'is_duplicate': False,
                'fraud_score': 0,
                'message': 'Transaction ID is unique'
            }
            
    except Exception as e:
        logger.error(f"Transaction ID duplicate check failed: {e}")
        return {
            'is_duplicate': False,
            'fraud_score': 0,
            'message': f'Check failed: {str(e)}'
        }
