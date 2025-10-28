
"""
Keyboard layouts and inline markup generators
"""
from typing import List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from config import CallbackPrefix
from database.models import Enrollment # Import Enrollment for type hinting

def main_menu_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Creates the persistent Reply Keyboard for the main menu.
    """
    keyboard = [
        [KeyboardButton("1- الدورات المتاحة 📚")],
        [KeyboardButton("2- دوراتي 📋")],
        [KeyboardButton("3- حول البوت ℹ️")],
        [KeyboardButton("📞 التواصل مع الإدارة")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def courses_menu_keyboard() -> InlineKeyboardMarkup:
    """Courses submenu keyboard (remains Inline)"""
    keyboard = [
        [InlineKeyboardButton("1- تفاصيل الدورات 📖", callback_data="course_details_menu")],
        [InlineKeyboardButton("2- التسجيل في الدورات 🛒", callback_data="course_selection_menu")],
        [InlineKeyboardButton("→ العودة للقائمة الرئيسية", callback_data=CallbackPrefix.BACK_MAIN)]
    ]
    return InlineKeyboardMarkup(keyboard)

def course_details_keyboard(courses: List, page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """Dynamic keyboard for course details browsing"""
    keyboard = []
    start = page * per_page
    end = min(start + per_page, len(courses))
    current_courses = courses[start:end]
    for course in current_courses:
        keyboard.append([
            InlineKeyboardButton(
                f"📖 {course.course_name}",
                callback_data=f"{CallbackPrefix.COURSE_DETAIL}{course.course_id}"
            )
        ])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"course_details_page_{page-1}"))
    if end < len(courses):
        nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data=f"course_details_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("→ عودة", callback_data=CallbackPrefix.BACK_COURSES)])
    return InlineKeyboardMarkup(keyboard)

def course_selection_keyboard(courses: list, selected_course_ids: list, cart_total: float) -> InlineKeyboardMarkup:
    """
    Dynamic keyboard for course selection with checkboxes
    Shows course name WITH PRICE, enrollment status, and cart total
    """
    keyboard = []
    
    for course in courses:
        is_selected = course.course_id in selected_course_ids
        
        # Check if course is full
        enrolled_count = getattr(course, 'enrolled_count', 0)
        is_full = course.max_students and enrolled_count >= course.max_students
        
        # Build button text WITH PRICE - UPDATED
        if is_selected:
            button_text = f"✅ {course.course_name}: {course.price:.0f} جنيه"
            callback_data = f"{CallbackPrefix.COURSE_DESELECT}{course.course_id}"
        elif is_full:
            button_text = f"❌ {course.course_name}: {course.price:.0f} جنيه (ممتلئة)"
            callback_data = "course_full"
        else:
            button_text = f"⭕ {course.course_name}: {course.price:.0f} جنيه"
            callback_data = f"{CallbackPrefix.COURSE_SELECT}{course.course_id}"
        
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Bottom action buttons
    action_buttons = []
    
    if selected_course_ids:
        action_buttons.append(InlineKeyboardButton(
            f"🛒 عرض السلة ({len(selected_course_ids)})", 
            callback_data="view_cart"
        ))
        action_buttons.append(InlineKeyboardButton(
            "✅ تأكيد", 
            callback_data="confirm_cart"
        ))
    
    if action_buttons:
        keyboard.append(action_buttons)
    
    # Cart total display - ALREADY IMPLEMENTED
    if cart_total > 0:
        keyboard.append([InlineKeyboardButton(
            f"💰 المجموع: {cart_total:.0f} جنيه سوداني",
            callback_data="cart_total_display"
        )])
    
    # Back button
    keyboard.append([InlineKeyboardButton(
        "→ العودة للقائمة الرئيسية",
        callback_data=CallbackPrefix.BACK_MAIN
    )])
    
    return InlineKeyboardMarkup(keyboard)


def course_detail_keyboard(course_id: int) -> InlineKeyboardMarkup:
    """Keyboard for individual course detail view"""
    keyboard = [
        [InlineKeyboardButton("→ العودة للدورات", callback_data="course_details_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def cart_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for cart confirmation before payment"""
    keyboard = [
        [InlineKeyboardButton("1- إنشاء طلب الدفع 💳", callback_data="proceed_payment")],
        [InlineKeyboardButton("2- تعديل الاختيار ✏️", callback_data="course_selection_menu")],
        [InlineKeyboardButton("→ العودة للقائمة الرئيسية", callback_data=CallbackPrefix.BACK_MAIN)]
    ]
    return InlineKeyboardMarkup(keyboard)

def my_courses_selection_keyboard(pending_enrollments: List[Enrollment], selected_ids: List[int]) -> InlineKeyboardMarkup:
    """New keyboard for selecting pending courses to pay for - SHOWS REMAINING BALANCE"""
    keyboard = []
    
    # Course selection buttons (checklist style, no numbering)
    for enrollment in pending_enrollments:
        is_selected = enrollment.enrollment_id in selected_ids
        icon = "✅" if is_selected else "⬜"
        course_name = enrollment.course.course_name if enrollment.course else "دورة محذوفة"
        
        # ✅ CALCULATE REMAINING AMOUNT (not full amount)
        total_price = enrollment.payment_amount or 0.0
        paid_amount = enrollment.amount_paid or 0.0
        remaining = total_price - paid_amount
        
        # Show remaining amount instead of full amount
        button_text = f"{icon} {course_name} ({remaining:.0f} جنيه)"
        
        # FIXED: Typo `mycourse_` changed to `my_course_` to match handler pattern
        callback_data = (
            f"my_course_deselect_{enrollment.enrollment_id}" if is_selected
            else f"my_course_select_{enrollment.enrollment_id}"
        )
        
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Action buttons
    if selected_ids:
        action_buttons = [
            InlineKeyboardButton("دفع المحدد 💳", callback_data="pay_selected_pending"),
            InlineKeyboardButton("إلغاء المحدد 🗑️", callback_data="cancel_selected_pending")
        ]
        keyboard.append(action_buttons)
    
    # Back button
    keyboard.append([InlineKeyboardButton("→ العودة للقائمة الرئيسية", callback_data=CallbackPrefix.BACK_MAIN)])
    
    return InlineKeyboardMarkup(keyboard)


def payment_upload_keyboard() -> InlineKeyboardMarkup:
    """Keyboard during receipt upload process"""
    keyboard = [
        [InlineKeyboardButton("❌ إلغاء الدفع", callback_data="cancel_payment")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Simple back to main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("→ العودة للقائمة الرئيسية", callback_data=CallbackPrefix.BACK_MAIN)]
    ]
    return InlineKeyboardMarkup(keyboard)

# Admin keyboards remain in English for clarity
def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Admin menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("1- View Statistics 📊", callback_data="admin_stats")],
        [InlineKeyboardButton("2- Pending Transactions 📋", callback_data="admin_pending")],
        [InlineKeyboardButton("3- Pending Registrations 💳", callback_data="admin_pending_registrations")],  # NEW
        [InlineKeyboardButton("← Back to Main Menu", callback_data=CallbackPrefix.BACK_MAIN)]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_transaction_keyboard(transaction_id: int) -> InlineKeyboardMarkup:
    """Keyboard for admin to approve/reject transactions"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"{CallbackPrefix.ADMIN_APPROVE}{transaction_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"{CallbackPrefix.ADMIN_REJECT}{transaction_id}")
        ],
        [InlineKeyboardButton("← Back to Pending", callback_data="admin_pending")]
    ]
    return InlineKeyboardMarkup(keyboard)


def cart_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for viewing and managing cart"""
    keyboard = [
        [InlineKeyboardButton("✅ تأكيد والمتابعة للدفع", callback_data=CallbackPrefix.CONFIRM_CART)],
        [InlineKeyboardButton("✏️ تعديل السلة", callback_data="course_selection_menu")],
        [InlineKeyboardButton("🗑️ إفراغ السلة", callback_data=CallbackPrefix.CLEAR_CART)],
        [InlineKeyboardButton("→ العودة للقائمة الرئيسية", callback_data=CallbackPrefix.BACK_MAIN)]
    ]
    return InlineKeyboardMarkup(keyboard)

def failed_receipt_admin_keyboard(enrollment_ids_str: str, telegram_user_id: int) -> InlineKeyboardMarkup:
    """
    Keyboard for admin to approve/reject a failed receipt immediately
    Args:
        enrollment_ids_str: Comma-separated enrollment IDs
        telegram_user_id: User's Telegram ID for reference
    """
    callback_data = f"{enrollment_ids_str}|{telegram_user_id}"
    keyboard = [
        [
            InlineKeyboardButton("✅ قبول / Approve", callback_data=f"{CallbackPrefix.ADMIN_APPROVE_FAILED}{callback_data}"),
            InlineKeyboardButton("❌ رفض / Reject", callback_data=f"{CallbackPrefix.ADMIN_REJECT_FAILED}{callback_data}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def certificate_option_keyboard(course_id: int) -> InlineKeyboardMarkup:
    """
    Keyboard to ask user if they want certificate
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ مع شهادة (With Certificate)", callback_data=f"cert_yes_{course_id}"),
        ],
        [
            InlineKeyboardButton("❌ بدون شهادة (Without Certificate)", callback_data=f"cert_no_{course_id}"),
        ],
        [
            InlineKeyboardButton("🔙 العودة (Back)", callback_data="course_selection_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ADD this NEW function to keyboards.py

def course_info_buttons_keyboard(course_id: int) -> InlineKeyboardMarkup:
    """Button menu for course details"""
    keyboard = [
        [InlineKeyboardButton("📋 الوصف | Description", callback_data=f"course_desc_{course_id}")],
        [InlineKeyboardButton("📅 التواريخ | Dates", callback_data=f"course_dates_{course_id}")],
        [InlineKeyboardButton("→ عودة لقائمة الدورات", callback_data="course_details_menu")],
        [InlineKeyboardButton("→ العودة للقائمة الرئيسية", callback_data=CallbackPrefix.BACK_MAIN)]
    ]
    return InlineKeyboardMarkup(keyboard)
