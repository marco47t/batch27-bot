"""
AWS S3 Storage Helper
"""
import boto3
from botocore.exceptions import ClientError
import config
import logging
from datetime import datetime
import os

logger = logging.getLogger(__name__)

# Don't initialize at import time - do it lazily
_s3_client = None

def get_s3_client():
    """Get or create S3 client (lazy initialization)"""
    global _s3_client
    
    if _s3_client is None:
        # Check if credentials are configured
        if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
            logger.warning("AWS credentials not configured - S3 storage disabled")
            return None
        
        try:
            _s3_client = boto3.client(
                's3',
                aws_access_key_id=config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
                region_name=config.AWS_S3_REGION
            )
            logger.info("✅ S3 client initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize S3 client: {e}")
            return None
    
    return _s3_client


def upload_receipt_to_s3(file_path: str, user_id: int, enrollment_id: int) -> str:
    """
    Upload receipt image to S3
    Returns: S3 URL of uploaded file
    """
    s3_client = get_s3_client()
    
    if not s3_client:
        logger.warning("S3 not configured - skipping upload")
        raise Exception("S3 storage not configured")
    
    try:
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_extension = os.path.splitext(file_path)[1]
        s3_key = f"receipts/{user_id}/{enrollment_id}_{timestamp}{file_extension}"
        
        # Upload to S3
        s3_client.upload_file(
            file_path,
            config.AWS_S3_BUCKET_NAME,
            s3_key,
            ExtraArgs={'ContentType': 'image/jpeg'}
        )
        
        # Generate URL
        s3_url = f"https://{config.AWS_S3_BUCKET_NAME}.s3.{config.AWS_S3_REGION}.amazonaws.com/{s3_key}"
        
        logger.info(f"✅ Uploaded receipt to S3: {s3_url}")
        return s3_url
        
    except ClientError as e:
        logger.error(f"❌ Failed to upload to S3: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error uploading to S3: {e}")
        raise


def download_receipt_from_s3(s3_url: str, local_path: str) -> str:
    """
    Download receipt from S3 to local path
    Returns: Local file path
    """
    s3_client = get_s3_client()
    
    if not s3_client:
        logger.warning("S3 not configured - cannot download")
        raise Exception("S3 storage not configured")
    
    try:
        # Extract S3 key from URL
        s3_key = s3_url.split(f"{config.AWS_S3_BUCKET_NAME}.s3.{config.AWS_S3_REGION}.amazonaws.com/")[1]
        
        # Download from S3
        s3_client.download_file(
            config.AWS_S3_BUCKET_NAME,
            s3_key,
            local_path
        )
        
        logger.info(f"✅ Downloaded receipt from S3: {local_path}")
        return local_path
        
    except ClientError as e:
        logger.error(f"❌ Failed to download from S3: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error downloading from S3: {e}")
        raise


def delete_receipt_from_s3(s3_url: str):
    """Delete receipt from S3"""
    s3_client = get_s3_client()
    
    if not s3_client:
        logger.warning("S3 not configured - cannot delete")
        return
    
    try:
        # Extract S3 key from URL
        s3_key = s3_url.split(f"{config.AWS_S3_BUCKET_NAME}.s3.{config.AWS_S3_REGION}.amazonaws.com/")[1]
        
        # Delete from S3
        s3_client.delete_object(
            Bucket=config.AWS_S3_BUCKET_NAME,
            Key=s3_key
        )
        
        logger.info(f"✅ Deleted receipt from S3: {s3_url}")
        
    except ClientError as e:
        logger.error(f"❌ Failed to delete from S3: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error deleting from S3: {e}")
        raise


def is_s3_configured() -> bool:
    """Check if S3 is properly configured"""
    return bool(
        config.AWS_ACCESS_KEY_ID and 
        config.AWS_SECRET_ACCESS_KEY and 
        config.AWS_S3_BUCKET_NAME
    )
