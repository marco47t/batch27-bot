"""
Message templates and formatters
"""

from typing import List
from datetime import datetime
from database.models import Course, Enrollment, Transaction
import config

def welcome_message() -> str:
    """Welcome message for new users"""
    return """
🎓 أهلاً بك في بوت تسجيل الدورات!

اختر ما تود القيام به من القائمة أدناه:

📚 الدورات المتاحة - تصفح الدورات المتاحة وقم بالتسجيل

📋 دوراتي - عرض الدورات التي سجلت بها وحالة الدفع

ℹ️ حول البوت - شرح لكيفية استخدام البوت

اختر أحد الخيارات للبدء!
"""

def about_bot_message() -> str:
    """About the bot message"""
    return """
ℹ️ حول البوت

هذا البوت مصمم لمساعدتك في:

1️⃣ تصفح الدورات: يمكنك استعراض جميع الدورات المتاحة وتفاصيلها.

2️⃣ التسجيل: يمكنك اختيار دورة أو أكثر وإضافتها إلى قائمة التسجيل.

3️⃣ الدفع: بعد تأكيد اختيارك، سيتم إنشاء طلبات دفع في قسم "دوراتي".

4️⃣ تأكيد الدفع: اذهب إلى "دوراتي"، اختر الطلبات التي تريد دفعها، ثم ارفع صورة إيصال الدفع.

5️⃣ الانضمام: بعد التحقق من الدفع، ستتمكن من الانضمام إلى مجموعات الدورة.

استمتع بتجربتك! 🎉
"""

def courses_menu_message() -> str:
    return """
📚 قائمة الدورات

اختر ما تريد:

1️⃣ تفاصيل الدورات - عرض معلومات مفصلة عن كل دورة
2️⃣ التسجيل في الدورات - اختر الدورات وأضفها للسلة
"""

def course_list_message(courses: list, enrollment_counts: dict = None) -> str:
    """Display list of courses with capacity info"""
    if not courses:
        return "❌ لا توجد دورات متاحة حالياً."
    
    message = "📚 الدورات المتاحة:\n\n"
    
    for course in courses:
        enrolled = enrollment_counts.get(course.course_id, 0) if enrollment_counts else 0
        capacity_text = ""
        
        if course.max_students:
            remaining = course.max_students - enrolled
            if remaining <= 0:
                capacity_text = f" - ❌ ممتلئة ({enrolled}/{course.max_students})"
            elif remaining <= 5:
                capacity_text = f" - ⚠️ {remaining} مقاعد متبقية ({enrolled}/{course.max_students})"
            else:
                capacity_text = f" - ✅ متاحة ({enrolled}/{course.max_students})"
        
        message += f"🎓 {course.course_name}\n"
        message += f"💰 السعر: {course.price:.0f} جنيه{capacity_text}\n\n"
    
    return message

def course_detail_message(course, enrollment_count: int = 0) -> str:
    """Display detailed course information with all dates"""
    from datetime import datetime
    
    # Capacity information
    capacity_info = ""
    if course.max_students:
        remaining = course.max_students - enrollment_count
        capacity_info = f"\n👥 المسجلين: {enrollment_count}/{course.max_students}"
        if remaining <= 0:
            capacity_info += "\n⚠️ الدورة ممتلئة حالياً"
        elif remaining <= 5:
            capacity_info += f"\n⚠️ فقط {remaining} مقاعد متبقية!"
    
    # Registration period information
    registration_info = ""
    if course.registration_open_date or course.registration_close_date:
        registration_info = "\n\n📅 فترة التسجيل / Registration Period:"
        
        if course.registration_open_date:
            reg_open_str = course.registration_open_date.strftime('%Y-%m-%d')
            registration_info += f"\n🟢 يفتح / Opens: {reg_open_str}"
            
            # Check if registration is open yet
            if datetime.now() < course.registration_open_date:
                registration_info += " (قريباً / Coming Soon)"
        
        if course.registration_close_date:
            reg_close_str = course.registration_close_date.strftime('%Y-%m-%d')
            registration_info += f"\n🔴 يغلق / Closes: {reg_close_str}"
            
            # Check if registration has closed
            if datetime.now() > course.registration_close_date:
                registration_info += " (مغلق / Closed)"
    
    # Course period information
    course_period_info = ""
    if course.start_date or course.end_date:
        course_period_info = "\n\n📚 مدة الدورة / Course Duration:"
        
        if course.start_date:
            start_str = course.start_date.strftime('%Y-%m-%d')
            course_period_info += f"\n▶️ البداية / Start: {start_str}"
        
        if course.end_date:
            end_str = course.end_date.strftime('%Y-%m-%d')
            course_period_info += f"\n🏁 النهاية / End: {end_str}"
    
    return f"""
📖 تفاصيل الدورة

🎓 الاسم: {course.course_name}

📝 الوصف: {course.description or 'لا يوجد وصف'}

💰 السعر: {course.price:.0f} جنيه سوداني{capacity_info}{registration_info}{course_period_info}

🔗 رابط المجموعة: {course.telegram_group_link or 'سيتم توفيره بعد التسجيل'}
"""


def receipt_processing_message() -> str:
    return "⏳ جاري معالجة الإيصال...\n\nيرجى الانتظار بينما نتحقق من الدفع..."

def payment_success_message(courses_data, group_links=None):
    """Generate payment success message with course list"""
    message = "✅ <b>تم قبول الدفعة بنجاح!</b>\n\n"
    message += "<b>الدورات المسجلة:</b>\n"
    
    for idx, course in enumerate(courses_data, 1):
        message += f"{idx}. {course['course_name']}\n"
    
    if group_links:
        message += "\n🔗 <b>روابط المجموعات:</b>\n"
        for link in group_links:
            message += f"• {link}\n"
    
    message += "\nشكراً لك! 🎉"
    return message

def payment_failed_message(reason: str) -> str:
    """Format payment failure message - simplified"""
    # Determine issue type
    if "does not match" in reason or "account" in reason.lower():
        issue = "❌ رقم الحساب غير صحيح"
        details = f"الرقم المرسل إليه لا يطابق: {config.EXPECTED_ACCOUNT_NUMBER}"
    elif "amount" in reason.lower() and ("below" in reason.lower() or "less" in reason.lower()):
        issue = "❌ المبلغ أقل من المطلوب"
        details = "المبلغ المحول أقل من المبلغ المطلوب"
    elif "not readable" in reason.lower() or "unclear" in reason.lower():
        issue = "❌ الصورة غير واضحة"
        details = "لا يمكن قراءة تفاصيل الإيصال"
    else:
        issue = "❌ فشل التحقق من الإيصال"
        details = "فشل التحقق التلقائي من الإيصال"
    
    return f"""
{issue}

⚠️ المشكلة:
{details}

💡 ما يجب فعله:
✓ تأكد من وضوح الصورة
✓ تحقق من رقم الحساب: {config.EXPECTED_ACCOUNT_NUMBER}
✓ تأكد من المبلغ المحول بالجنيه السوداني (SDG)

سيتم مراجعة الإيصال يدوياً من قبل الإدارة.
"""

def my_courses_message(enrollments: list, pending_count: int = 0, selected_count: int = 0, total_selected: float = 0.0) -> str:
    """Display user's enrolled courses with selection status"""
    if not enrollments:
        return "📋 لا توجد دورات مسجلة\n\nسجل في الدورات من القائمة الرئيسية."
    
    verified = [e for e in enrollments if e.payment_status.value == "VERIFIED"]
    pending = [e for e in enrollments if e.payment_status.value == "PENDING"]
    failed = [e for e in enrollments if e.payment_status.value == "FAILED"]
    
    message = "📋 دوراتي:\n\n"
    
    if verified:
        message += "✅ الدورات المفعلة:\n"
        for e in verified:
            message += f"• {e.course.course_name}\n"
        message += "\n"
    
    if pending:
        message += "⏳ قيد المراجعة:\n"
        for e in pending:
            message += f"• {e.course.course_name}\n"
        message += "\n"
    
    if failed:
        message += "❌ تحتاج إعادة محاولة:\n"
        for e in failed:
            message += f"• {e.course.course_name}\n"
        message += "\n"
    
    if pending_count > 0:
        message += f"\n📝 الدورات المعلقة: {pending_count}\n"
        if selected_count > 0:
            message += f"✓ المحدد للدفع: {selected_count}\n"
            message += f"💰 المبلغ الإجمالي: {total_selected:.0f} جنيه\n"
    
    return message

def admin_stats_message(stats: dict) -> str:
    """Format admin statistics message"""
    return f"""
📊 إحصائيات التسجيل

📝 إجمالي التسجيلات: {stats['total_enrollments']}
✅ الدفعات الموثقة: {stats['verified_payments']}
⏳ الدفعات المعلقة: {stats['pending_payments']}
❌ الدفعات الفاشلة: {stats['failed_payments']}
💰 إجمالي الإيرادات: {stats['total_revenue']:.0f} جنيه

🔍 إيصالات تنتظر المراجعة: {stats.get('pending_transactions', 0)}
"""

def admin_transaction_message(transaction) -> str:
    enrollment = transaction.enrollment
    user = enrollment.user
    course = enrollment.course
    
    return f"""
📋 معاملة رقم {transaction.transaction_id}

👤 المستخدم: {user.first_name} {user.last_name or ''}
   (@{user.username or 'لا يوجد'})
   ID: {user.telegram_user_id}

🎓 الدورة: {course.course_name}
💰 المبلغ المتوقع: {enrollment.payment_amount:.0f} جنيه

📅 تاريخ الإرسال: {transaction.submitted_date.strftime('%Y-%m-%d %H:%M')}

حالة المعاملة: {transaction.status.value}
"""

def error_message(error_type: str) -> str:
    errors = {
        "admin_only": "⛔ هذا الأمر متاح للمسؤولين فقط.",
        "cart_empty": "🛒 السلة فارغة. أضف دورات أولاً.",
        "course_not_found": "❌ الدورة غير موجودة.",
        "enrollment_not_found": "❌ التسجيل غير موجود.",
        "payment_data_missing": "❌ بيانات الدفع مفقودة. حاول مرة أخرى.",
        "payment_amount_missing": "❌ المبلغ المطلوب مفقود. حاول مرة أخرى.",
        "already_enrolled": "⚠️ أنت مسجل بالفعل في هذه الدورة.",
        "general": "❌ حدث خطأ. يرجى المحاولة لاحقاً."
    }
    
    return errors.get(error_type, errors["general"])


def admin_help_message():
    """Return admin help message with all available commands"""
    return """
🔧 **Admin Commands**

**Course Management:**
/addcourse - Add a new course
/editcourse - Edit existing course
/deletecourse - Delete a course (only if no students)
/listcourses - List all courses with stats
/togglecourse - Activate/Deactivate a course

**Student Management:**
/admin - Admin dashboard
  → View statistics
  → Review pending payments
  → Approve/Reject receipts

**Quick Tips:**
• Use /cancel to abort any operation
• Deactivated courses are hidden from students
• You can't delete courses with enrolled students
• All actions are logged

Need help? Contact the developer.
"""


def daily_summary_report_message(enrollments, date_str):
    """Generate daily summary report message"""
    if not enrollments:
        return f"📊 **Daily Report - {date_str}**\n\n✅ No new verified enrollments today."
    
    total_revenue = sum(e.payment_amount or 0 for e in enrollments)
    
    # Group by course
    from collections import defaultdict
    course_stats = defaultdict(lambda: {'count': 0, 'revenue': 0})
    
    for enrollment in enrollments:
        course_name = enrollment.course.course_name
        course_stats[course_name]['count'] += 1
        course_stats[course_name]['revenue'] += enrollment.payment_amount or 0
    
    # Build message
    message = f"📊 **Daily Summary Report**\n"
    message += f"📅 Date: {date_str}\n\n"
    message += f"**Total Verified Enrollments:** {len(enrollments)}\n"
    message += f"**Total Revenue:** ${total_revenue:,.2f}\n\n"
    message += "**Breakdown by Course:**\n"
    
    for course_name, stats in course_stats.items():
        message += f"\n📚 **{course_name}**\n"
        message += f"  • Students: {stats['count']}\n"
        message += f"  • Revenue: ${stats['revenue']:,.2f}\n"
    
    return message


def payment_instructions_message(amount: float) -> str:
    """Payment instructions message"""
    return f"""
💳 تعليمات الدفع

المبلغ المطلوب: {amount:.0f} جنيه سوداني (SDG)

🏦 تفاصيل الحساب:
رقم الحساب: {config.EXPECTED_ACCOUNT_NUMBER}

📸 بعد إتمام الدفع:
أرسل صورة واضحة من إيصال التحويل

⚠️ ملاحظات هامة:
✓ تأكد من وضوح جميع التفاصيل في الصورة
✓ يجب أن يظهر المبلغ: {amount:.0f} SDG
✓ يجب أن يتطابق رقم الحساب: {config.EXPECTED_ACCOUNT_NUMBER}

سيتم تأكيد تسجيلك فوراً بعد التحقق!
"""


def cart_message(courses: list, total: float) -> str:
    if not courses:
        return "🛒 سلة التسوق فارغة"
    
    message = "🛒 سلة التسوق:\n\n"
    for idx, course in enumerate(courses, 1):
        message += f"{idx}. {course.course_name} - {course.price:.0f} جنيه\n"
    
    message += f"\n💰 المجموع: {total:.0f} جنيه سوداني"
    return message

def receipt_processing_message() -> str:
    """Receipt is being processed"""
    return """
⏳ جاري معالجة الإيصال...

يتم الآن التحقق من صورة الإيصال.
قد تستغرق هذه العملية بضع ثوان.

الرجاء الانتظار...
"""


def payment_success_message(course_data_list: List[dict], group_links_list: List[str] = None) -> str:
    """Payment verified successfully with course details and group links"""
    
    if not course_data_list:
        return "✅ تم التحقق من الدفع بنجاح!"
    
    message = "✅ تم التحقق من الدفع بنجاح!\n\nتم تأكيد تسجيلك في:\n\n"
    
    for idx, course_data in enumerate(course_data_list):
        course_name = course_data.get('name', 'Unknown')
        message += f"🎓 {course_name}\n"
        
        # Add group link if available
        if group_links_list and idx < len(group_links_list) and group_links_list[idx]:
            message += f"🔗 رابط المجموعة: {group_links_list[idx]}\n"
        
        message += "\n"
    
    message += "🎉 مبروك! يمكنك الآن الوصول إلى الدورات من قسم \"دوراتي\""
    
    return message


def payment_failed_message(reason: str = None) -> str:
    """Payment verification failed"""
    base_message = """
❌ لم يتم التحقق من الإيصال

عذراً، لم نتمكن من التحقق من إيصال الدفع.
"""
    
    if reason:
        base_message += f"\n📝 السبب: {reason}\n"
    
    base_message += """
🔄 يرجى التحقق من:
• وضوح الصورة
• ظهور جميع التفاصيل
• المبلغ المدفوع صحيح
• رقم الحساب صحيح

يمكنك إعادة المحاولة بإرسال صورة جديدة.
"""
    return base_message