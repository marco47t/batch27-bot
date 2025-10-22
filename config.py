"""
Configuration file for Course Registration Bot
Loads environment variables and provides configuration constants
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env file")

ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
if not ADMIN_CHAT_ID:
    raise ValueError("ADMIN_CHAT_ID is not set in .env file")

# Convert admin chat ID to integer
try:
    ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)
except ValueError:
    raise ValueError("ADMIN_CHAT_ID must be a valid integer")

# Admin User IDs
ADMIN_USER_IDS_STR = os.getenv('ADMIN_USER_IDS', '')
ADMIN_USER_IDS = [int(uid.strip()) for uid in ADMIN_USER_IDS_STR.split(',') if uid.strip()]

# Gemini AI Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not set in .env file")

# Payment Configuration
# Payment Configuration - Multiple Account Numbers Support
# ✅ SUPPORTS MULTIPLE ACCOUNT NUMBERS (comma-separated in .env)
BANK_ACCOUNT_NUMBERS = os.getenv('BANK_ACCOUNT_NUMBERS', '1234567890')
EXPECTED_ACCOUNT_NAME = os.getenv('EXPECTED_ACCOUNT_NAME', 'School Account')

# ✅ Parse multiple accounts into a list
def get_expected_accounts():
    """
    Parse multiple account numbers from env variable
    Supports formats like: xxxx163485xxxx (masked accounts in receipts)
    Returns: list of account numbers
    """
    accounts_str = os.getenv('BANK_ACCOUNT_NUMBERS', '1234567890')
    return [acc.strip() for acc in accounts_str.split(',') if acc.strip()]

# Global list of expected account numbers
EXPECTED_ACCOUNTS = get_expected_accounts()

# Legacy support (use first account for backward compatibility)
EXPECTED_ACCOUNT_NUMBER = EXPECTED_ACCOUNTS[0] if EXPECTED_ACCOUNTS else '1234567890'

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///course_bot.db')

# Application Settings
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Receipt Storage
RECEIPTS_DIR = 'receipts'
os.makedirs(RECEIPTS_DIR, exist_ok=True)

ADMIN_REGISTRATION_PASSWORD = "7B5413af#"

ADMIN_REGISTRATION_PASSWORD = os.getenv('ADMIN_REGISTRATION_PASSWORD')
if not ADMIN_REGISTRATION_PASSWORD:
    raise ValueError("ADMIN_REGISTRATION_PASSWORD is not set in .env file")
# Conversation States
class States:
    """Conversation handler states"""
    MAIN_MENU = 0
    COURSES_MENU = 1
    COURSE_DETAILS = 2
    COURSE_SELECTION = 3
    CART_REVIEW = 4
    RECEIPT_UPLOAD = 5
    RECEIPT_PROCESSING = 6
    MY_COURSES = 7
    PAYMENT_STATUS = 8
    ADMIN_MENU = 9
    
# Callback Data Prefixes
class CallbackPrefix:
    """Callback query data prefixes"""
    COURSES_MENU = "courses_menu"
    COURSE_DETAIL = "course_detail_"
    COURSE_SELECT = "course_select_"
    COURSE_DESELECT = "course_deselect_"
    CONFIRM_CART = "confirm_cart"
    CLEAR_CART = "clear_cart"
    BACK_MAIN = "back_main"
    BACK_COURSES = "back_courses"
    MY_COURSES = "my_courses"
    PAY_PENDING = "pay_pending_"
    ADMIN_APPROVE = "admin_approve_"
    ADMIN_REJECT = "admin_reject_"
    ADMIN_APPROVE_FAILED = "admin_approve_failed_"
    ADMIN_REJECT_FAILED = "admin_reject_failed_"

# Message Templates
class Messages:
    """Bot message templates"""
    WELCOME = """
👋 Welcome to the Course Registration Bot!

Please select an option from the menu below:
"""
    
    COURSES_MENU = """
📚 **Courses Menu**

What would you like to do?
"""
    
    CART_SUMMARY = """
🛒 **Your Cart**

Selected Courses: {count}
Total Amount: ${total}

{courses_list}
"""
    
    PAYMENT_INSTRUCTIONS = """
💳 **Payment Instructions**

Please transfer ${amount} to:
Account Number: {account_number}
Account Name: {account_name}

After making the payment, send a clear photo of your receipt.
"""
    
    RECEIPT_PROCESSING = """
⏳ Processing your receipt...

Please wait while we verify your payment.
"""
    
    PAYMENT_SUCCESS = """
✅ **Payment Verified!**

You have been successfully enrolled in:
{courses_list}

You can now join the course group(s):
{group_links}
"""
    
    PAYMENT_FAILED = """
❌ **Payment Verification Failed**

{reason}

Please try again with a valid receipt or contact support.
"""

# Gemini Prompt Template
RECEIPT_VALIDATION_PROMPT = """
Analyze this payment receipt image and extract the following information in JSON format:

{
  "account_number": "extracted account number",
  "amount": "extracted amount as number",
  "date": "extracted date in YYYY-MM-DD format",
  "transaction_id": "transaction or reference number if available",
  "is_valid": true/false,
  "notes": "any additional observations"
}

Look for:
- Account number or recipient information
- Payment amount (look for currency symbols)
- Transaction date
- Any reference or transaction ID

Return ONLY the JSON object, no additional text.
"""

def is_admin(user_id: int) -> bool:
    """Check if user is an admin"""
    return user_id in ADMIN_USER_IDS

def get_config_summary() -> str:
    """Return configuration summary for debugging"""
    return f"""
Configuration Summary:
- Environment: {ENVIRONMENT}
- Log Level: {LOG_LEVEL}
- Database: {DATABASE_URL}
- Admin User IDs: {len(ADMIN_USER_IDS)}
- Receipts Directory: {RECEIPTS_DIR}
"""

# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_S3_BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME', 'course-bot-receipts')
AWS_S3_REGION = os.getenv('AWS_S3_REGION', 'euw-north-1')
