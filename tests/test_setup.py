"""
Pre-Deployment Test Suite
Run this to verify all systems before going live
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db, init_db, crud
from database.models import User, Course, Enrollment, PaymentStatus
import config

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_test(name, passed, message=""):
    status = f"{Colors.GREEN}✅ PASS{Colors.END}" if passed else f"{Colors.RED}❌ FAIL{Colors.END}"
    print(f"{status} - {name}")
    if message:
        print(f"    {message}")

def test_environment():
    """Test environment variables"""
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}TESTING ENVIRONMENT CONFIGURATION{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    required_vars = [
        'BOT_TOKEN',
        'GEMINI_API_KEY',
        'ADMIN_USER_IDS',
        'DATABASE_URL'
    ]
    
    all_passed = True
    for var in required_vars:
        value = getattr(config, var, None)
        passed = value is not None and value != ""
        print_test(f"Environment: {var}", passed, f"Value: {'SET' if passed else 'MISSING'}")
        all_passed = all_passed and passed
    
    # Check admin password
    passed = hasattr(config, 'ADMIN_REGISTRATION_PASSWORD') and config.ADMIN_REGISTRATION_PASSWORD
    print_test("Admin registration password", passed)
    all_passed = all_passed and passed
    
    return all_passed

def test_database():
    """Test database connectivity and structure"""
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}TESTING DATABASE{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    all_passed = True
    
    try:
        # Test database initialization
        init_db()
        print_test("Database initialization", True)
        
        # Test database connection
        with get_db() as session:
            # Test creating a user
            test_user = crud.get_or_create_user(
                session,
                telegram_user_id=999999999,
                username="test_user",
                first_name="Test",
                last_name="User"
            )
            session.commit()
            print_test("Create test user", True, f"User ID: {test_user.user_id}")
            
            # Test creating a course
            test_course = crud.create_course(
                session,
                course_name="Test Course",
                description="Test Description",
                price=100.0,
                max_students=50
            )
            session.commit()
            print_test("Create test course", True, f"Course ID: {test_course.course_id}")
            
            # Test enrollment
            enrollment = crud.create_enrollment(
                session,
                user_id=test_user.telegram_user_id,
                course_id=test_course.course_id,
                payment_amount=100.0
            )
            session.commit()
            print_test("Create test enrollment", True, f"Enrollment ID: {enrollment.enrollment_id}")
            
            # Clean up test data
            session.delete(enrollment)
            session.delete(test_course)
            session.delete(test_user)
            session.commit()
            print_test("Cleanup test data", True)
            
    except Exception as e:
        print_test("Database operations", False, f"Error: {str(e)}")
        all_passed = False
    
    return all_passed

def test_file_structure():
    """Test that all required files exist"""
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}TESTING FILE STRUCTURE{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    required_files = [
        'main.py',
        'config.py',
        '.env',
        'database/__init__.py',
        'database/models.py',
        'database/crud.py',
        'handlers/menu_handlers.py',
        'handlers/course_handlers.py',
        'handlers/admin_handlers.py',
        'handlers/payment_handlers.py',
        'handlers/group_handlers.py',
        'handlers/admin_course_management.py',
        'handlers/admin_registration.py',
        'handlers/group_registration.py',
        'utils/keyboards.py',
        'utils/messages.py',
        'utils/helpers.py',
        'services/gemini_service.py',
    ]
    
    all_passed = True
    for file_path in required_files:
        exists = Path(file_path).exists()
        print_test(f"File: {file_path}", exists)
        all_passed = all_passed and exists
    
    return all_passed

def test_imports():
    """Test that all modules can be imported"""
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}TESTING MODULE IMPORTS{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    modules = [
        'database',
        'handlers.menu_handlers',
        'handlers.course_handlers',
        'handlers.admin_handlers',
        'handlers.payment_handlers',
        'handlers.admin_course_management',
        'handlers.admin_registration',
        'handlers.group_registration',
        'utils.keyboards',
        'utils.messages',
        'services.gemini_service',
    ]
    
    all_passed = True
    for module in modules:
        try:
            __import__(module)
            print_test(f"Import: {module}", True)
        except Exception as e:
            print_test(f"Import: {module}", False, f"Error: {str(e)}")
            all_passed = False
    
    return all_passed

def generate_deployment_checklist():
    """Generate deployment checklist"""
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}DEPLOYMENT CHECKLIST{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    checklist = """
    📋 PRE-DEPLOYMENT CHECKLIST
    
    ✓ Environment Variables:
      □ BOT_TOKEN configured
      □ GEMINI_API_KEY configured
      □ ADMIN_USER_IDS set
      □ ADMIN_REGISTRATION_PASSWORD set
      □ Database configured
    
    ✓ Database:
      □ Database initialized
      □ Database migrations applied
      □ is_admin column added to users table
      □ telegram_group_id column added to courses table
    
    ✓ Bot Setup:
      □ Bot created via @BotFather
      □ Bot commands set (@BotFather /setcommands)
      □ Bot privacy mode disabled (for group commands)
    
    ✓ Testing (Manual):
      □ /start command works
      □ Main menu buttons work
      □ Course browsing works
      □ Admin registration works (/register)
      □ Course creation works (/addcourse)
      □ Group registration works (/register_group)
      □ Payment upload works
      □ Receipt verification works
      □ Admin approval/rejection works
      □ Group auto-join works
    
    ✓ Deployment:
      □ Choose hosting platform (Railway/Heroku/VPS)
      □ Environment variables set on platform
      □ Database backed up
      □ Bot deployed and running
      □ Logs monitoring configured
      □ Error alerts configured
    """
    
    print(checklist)

def main():
    """Run all tests"""
    print(f"\n{Colors.YELLOW}{'='*60}{Colors.END}")
    print(f"{Colors.YELLOW}COURSE REGISTRATION BOT - PRE-DEPLOYMENT TESTS{Colors.END}")
    print(f"{Colors.YELLOW}{'='*60}{Colors.END}")
    
    results = {
        "Environment": test_environment(),
        "File Structure": test_file_structure(),
        "Module Imports": test_imports(),
        "Database": test_database(),
    }
    
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}TEST SUMMARY{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    all_passed = True
    for test_name, passed in results.items():
        status = f"{Colors.GREEN}✅ PASSED{Colors.END}" if passed else f"{Colors.RED}❌ FAILED{Colors.END}"
        print(f"{test_name:20} {status}")
        all_passed = all_passed and passed
    
    print()
    
    if all_passed:
        print(f"{Colors.GREEN}{'='*60}{Colors.END}")
        print(f"{Colors.GREEN}✅ ALL TESTS PASSED - READY FOR DEPLOYMENT{Colors.END}")
        print(f"{Colors.GREEN}{'='*60}{Colors.END}\n")
        generate_deployment_checklist()
    else:
        print(f"{Colors.RED}{'='*60}{Colors.END}")
        print(f"{Colors.RED}❌ SOME TESTS FAILED - FIX ISSUES BEFORE DEPLOYMENT{Colors.END}")
        print(f"{Colors.RED}{'='*60}{Colors.END}\n")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
