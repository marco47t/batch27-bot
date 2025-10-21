"""
CloudWatch Logging Configuration
Creates 3 separate log streams:
1. /batch27-bot/full - Everything (DEBUG level)
2. /batch27-bot/app - Application logs without HTTP noise (INFO level)
3. /batch27-bot/errors - Errors only (ERROR+ level)
"""

import logging
import sys
import watchtower
import boto3
from botocore.exceptions import ClientError


class HTTPFilter(logging.Filter):
    """Filter out HTTP request logs from httpx"""
    def filter(self, record):
        # Block httpx INFO logs about HTTP requests
        if 'httpx' in record.name and 'HTTP Request' in record.getMessage():
            return False
        return True


def setup_cloudwatch_logging(aws_region='us-east-1'):
    """
    Setup CloudWatch logging with 3 separate log groups
    """
    try:
        # Initialize CloudWatch client
        cloudwatch_client = boto3.client('logs', region_name=aws_region)
        
        # Root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)  # Capture everything at root level
        
        # Clear existing handlers to avoid duplicates
        root_logger.handlers.clear()
        
        # ==========================================
        # 1. CONSOLE HANDLER (for Railway logs)
        # ==========================================
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # ==========================================
        # 2. CLOUDWATCH: FULL LOGS (DEBUG)
        # ==========================================
        full_handler = watchtower.CloudWatchLogHandler(
            log_group='/batch27-bot/full',
            stream_name='debug-stream',
            boto3_client=cloudwatch_client,
            create_log_group=True
        )
        full_handler.setLevel(logging.DEBUG)
        full_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        full_handler.setFormatter(full_formatter)
        root_logger.addHandler(full_handler)
        
        # ==========================================
        # 3. CLOUDWATCH: APP LOGS (INFO, NO HTTP)
        # ==========================================
        app_handler = watchtower.CloudWatchLogHandler(
            log_group='/batch27-bot/app',
            stream_name='app-stream',
            boto3_client=cloudwatch_client,
            create_log_group=True
        )
        app_handler.setLevel(logging.INFO)
        app_handler.addFilter(HTTPFilter())  # Block HTTP noise
        app_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        app_handler.setFormatter(app_formatter)
        root_logger.addHandler(app_handler)
        
        # ==========================================
        # 4. CLOUDWATCH: ERRORS ONLY (ERROR+)
        # ==========================================
        error_handler = watchtower.CloudWatchLogHandler(
            log_group='/batch27-bot/errors',
            stream_name='error-stream',
            boto3_client=cloudwatch_client,
            create_log_group=True
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(pathname)s:%(lineno)d'
        )
        error_handler.setFormatter(error_formatter)
        root_logger.addHandler(error_handler)
        
        # ==========================================
        # 5. SUPPRESS NOISY LOGGERS
        # ==========================================
        # Suppress httpx at source
        logging.getLogger('httpx').setLevel(logging.WARNING)
        
        # Suppress boto3/botocore noise
        logging.getLogger('boto3').setLevel(logging.WARNING)
        logging.getLogger('botocore').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        
        print("✅ CloudWatch logging configured successfully!")
        print("📊 Log groups:")
        print("   - /batch27-bot/full (DEBUG - everything)")
        print("   - /batch27-bot/app (INFO - no HTTP)")
        print("   - /batch27-bot/errors (ERROR+ only)")
        
    except ClientError as e:
        print(f"⚠️ CloudWatch setup failed: {e}")
        print("Falling back to console logging only")
        
        # Fallback: console only
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
