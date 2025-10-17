"""
Admin course management handlers - Add, edit, delete courses via Telegram
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import crud, get_db
from utils.helpers import is_admin_user
from utils.keyboards import back_to_main_keyboard
import logging

logger = logging.getLogger(__name__)

# Conversation states
(COURSE_NAME, COURSE_DESCRIPTION, COURSE_PRICE,
COURSE_GROUP_LINK, COURSE_MAX_STUDENTS, COURSE_START_DATE, COURSE_END_DATE, 
COURSE_REG_OPEN_DATE, COURSE_REG_CLOSE_DATE, COURSE_CONFIRM,
EDIT_SELECT_COURSE, EDIT_SELECT_FIELD, EDIT_INPUT_VALUE) = range(13)

# ==================== /addcourse COMMAND ====================

async def add_course_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start conversation to add a new course"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.", reply_markup=back_to_main_keyboard())
        return ConversationHandler.END
    
    await update.message.reply_text(
        "➕ **إضافة كورس جديد / Add New Course**\n\n"
        "دعنا نبدأ! أدخل اسم الكورس:\n"
        "Let's start! Enter the course name:\n\n"
        "Send /cancel to abort.",
        parse_mode='Markdown'
    )
    
    context.user_data['new_course'] = {}
    return COURSE_NAME

async def course_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive course name"""
    course_name = update.message.text.strip()
    
    if len(course_name) < 3:
        await update.message.reply_text("❌ اسم الكورس قصير جداً. أدخل اسماً أطول.\nCourse name too short. Please enter a longer name.")
        return COURSE_NAME
    
    context.user_data['new_course']['name'] = course_name
    
    await update.message.reply_text(
        f"✅ الاسم: {course_name}\n\n"
        f"الآن أدخل وصف الكورس:\n"
        f"Now enter the course description:\n\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    
    return COURSE_DESCRIPTION

async def course_description_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive course description"""
    description = update.message.text.strip()
    
    if len(description) < 10:
        await update.message.reply_text("❌ الوصف قصير جداً. أدخل وصفاً أطول.\nDescription too short. Please enter a longer description.")
        return COURSE_DESCRIPTION
    
    context.user_data['new_course']['description'] = description
    
    await update.message.reply_text(
        f"✅ الوصف محفوظ / Description saved\n\n"
        f"الآن أدخل سعر الكورس (بالجنيه السوداني):\n"
        f"Now enter the course price (in SDG):\n\n"
        f"مثال / Example: 5000\n\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    
    return COURSE_PRICE

async def course_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive course price"""
    try:
        price = float(update.message.text.strip())
        
        if price <= 0:
            await update.message.reply_text("❌ السعر يجب أن يكون أكبر من صفر.\nPrice must be greater than zero.")
            return COURSE_PRICE
        
        context.user_data['new_course']['price'] = price
        context.user_data['new_course']['group_link'] = None  # Skip group link
        
        # GO DIRECTLY TO MAX STUDENTS (skip group link step)
        await update.message.reply_text(
            f"✅ السعر: {price:.2f} SDG\n\n"
            f"الآن أدخل العدد الأقصى للطلاب (أو أرسل 0 لعدد غير محدود):\n"
            f"Now enter the maximum number of students (or send 0 for unlimited):\n\n"
            f"مثال / Example: 50\n\n"
            f"Send /cancel to abort.",
            parse_mode='Markdown'
        )
        
        return COURSE_MAX_STUDENTS  # Skip COURSE_GROUP_LINK state
        
    except ValueError:
        await update.message.reply_text("❌ السعر غير صالح. أدخل رقماً.\nInvalid price. Please enter a number.")
        return COURSE_PRICE

async def course_group_link_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive course group link"""
    if update.message.text.strip().lower() == '/skip':
        context.user_data['new_course']['group_link'] = None
        await update.message.reply_text("⏭️ تخطي رابط المجموعة / Skipped group link")
    else:
        group_link = update.message.text.strip()
        
        # Basic validation
        if not (group_link.startswith('https://t.me/') or group_link.startswith('http://t.me/')):
            await update.message.reply_text(
                "❌ رابط غير صالح. يجب أن يبدأ بـ https://t.me/\n"
                "Invalid link. Must start with https://t.me/\n\n"
                "Send /skip to skip."
            )
            return COURSE_GROUP_LINK
        
        context.user_data['new_course']['group_link'] = group_link
        await update.message.reply_text(f"✅ الرابط: {group_link}")
    
    await update.message.reply_text(
        f"الآن أدخل العدد الأقصى للطلاب (أو أرسل 0 لعدد غير محدود):\n"
        f"Now enter the maximum number of students (or send 0 for unlimited):\n\n"
        f"مثال / Example: 50\n\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    
    return COURSE_MAX_STUDENTS

async def course_max_students_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive max students"""
    try:
        max_students = int(update.message.text.strip())
        
        if max_students < 0:
            await update.message.reply_text("❌ العدد لا يمكن أن يكون سالباً.\nNumber cannot be negative.")
            return COURSE_MAX_STUDENTS
                
        await update.message.reply_text(
            f"✅ العدد الأقصى: {max_students if max_students > 0 else 'غير محدود'}\n\n"
            f"الآن أدخل تاريخ بداية الكورس (YYYY-MM-DD):\n"
            f"Now enter the course start date (YYYY-MM-DD):\n\n"
            f"مثال / Example: 2025-11-01\n\n"
            f"Send /skip to skip this field.\n"
            f"Send /cancel to abort.",
            parse_mode='Markdown'
        )

        return COURSE_START_DATE
    except ValueError:
        await update.message.reply_text("❌ عدد غير صالح. أدخل رقماً.\nInvalid number. Please enter a number.")
        return COURSE_MAX_STUDENTS
    
async def course_start_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive course start date"""
    from datetime import datetime
    
    date_text = update.message.text.strip()
    
    if date_text.lower() == '/skip':
        context.user_data['new_course']['start_date'] = None
        await update.message.reply_text("⏭️ تخطي تاريخ البداية / Skipped start date")
    else:
        try:
            # Parse date in YYYY-MM-DD format
            start_date = datetime.strptime(date_text, '%Y-%m-%d')
            context.user_data['new_course']['start_date'] = start_date
            await update.message.reply_text(f"✅ تاريخ البداية: {date_text}")
        except ValueError:
            await update.message.reply_text(
                "❌ تنسيق غير صالح. استخدم YYYY-MM-DD\n"
                "Invalid format. Use YYYY-MM-DD\n\n"
                "Example: 2025-11-01\n\n"
                "Send /skip to skip."
            )
            return COURSE_START_DATE
    
    # Ask for end date
    await update.message.reply_text(
        f"الآن أدخل تاريخ نهاية الكورس (YYYY-MM-DD):\n"
        f"Now enter the course end date (YYYY-MM-DD):\n\n"
        f"مثال / Example: 2025-12-31\n\n"
        f"Send /skip to skip this field.\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    
    return COURSE_END_DATE

async def course_end_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive course end date"""
    from datetime import datetime
    
    date_text = update.message.text.strip()
    
    if date_text.lower() == '/skip':
        context.user_data['new_course']['end_date'] = None
        await update.message.reply_text("⏭️ تخطي تاريخ النهاية / Skipped end date")
    else:
        try:
            # Parse date in YYYY-MM-DD format
            end_date = datetime.strptime(date_text, '%Y-%m-%d')
            
            # Validate: end date should be after start date
            start_date = context.user_data['new_course'].get('start_date')
            if start_date and end_date < start_date:
                await update.message.reply_text(
                    "❌ تاريخ النهاية يجب أن يكون بعد تاريخ البداية.\n"
                    "End date must be after start date.\n\n"
                    "Send /skip to skip."
                )
                return COURSE_END_DATE
            
            context.user_data['new_course']['end_date'] = end_date
            await update.message.reply_text(f"✅ تاريخ النهاية: {date_text}")
        except ValueError:
            await update.message.reply_text(
                "❌ تنسيق غير صالح. استخدم YYYY-MM-DD\n"
                "Invalid format. Use YYYY-MM-DD\n\n"
                "Example: 2025-12-31\n\n"
                "Send /skip to skip."
            )
            return COURSE_END_DATE
        

        # Ask for registration open date
        await update.message.reply_text(
            f"الآن أدخل تاريخ فتح التسجيل (YYYY-MM-DD):\n"
            f"Now enter the registration opening date (YYYY-MM-DD):\n\n"
            f"مثال / Example: 2025-10-15\n\n"
            f"Send /skip to skip this field.\n"
            f"Send /cancel to abort.",
            parse_mode='Markdown'
        )

        return COURSE_REG_OPEN_DATE
async def course_reg_open_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive course registration opening date"""
    from datetime import datetime
    
    date_text = update.message.text.strip()
    
    if date_text.lower() == '/skip':
        context.user_data['new_course']['registration_open_date'] = None
        await update.message.reply_text("⏭️ تخطي تاريخ فتح التسجيل / Skipped registration opening date")
    else:
        try:
            # Parse date in YYYY-MM-DD format
            reg_open_date = datetime.strptime(date_text, '%Y-%m-%d')
            context.user_data['new_course']['registration_open_date'] = reg_open_date
            await update.message.reply_text(f"✅ تاريخ فتح التسجيل: {date_text}")
        except ValueError:
            await update.message.reply_text(
                "❌ تنسيق غير صالح. استخدم YYYY-MM-DD\n"
                "Invalid format. Use YYYY-MM-DD\n\n"
                "Example: 2025-10-15\n\n"
                "Send /skip to skip."
            )
            return COURSE_REG_OPEN_DATE
    
    # Ask for registration close date
    await update.message.reply_text(
        f"الآن أدخل تاريخ إغلاق التسجيل (YYYY-MM-DD):\n"
        f"Now enter the registration closing date (YYYY-MM-DD):\n\n"
        f"مثال / Example: 2025-10-25\n\n"
        f"Send /skip to skip this field.\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    
    return COURSE_REG_CLOSE_DATE

async def course_reg_close_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive course registration closing date"""
    from datetime import datetime
    
    date_text = update.message.text.strip()
    
    if date_text.lower() == '/skip':
        context.user_data['new_course']['registration_close_date'] = None
        await update.message.reply_text("⏭️ تخطي تاريخ إغلاق التسجيل / Skipped registration closing date")
    else:
        try:
            # Parse date in YYYY-MM-DD format
            reg_close_date = datetime.strptime(date_text, '%Y-%m-%d')
            
            # Validate: close date should be after open date
            reg_open_date = context.user_data['new_course'].get('registration_open_date')
            if reg_open_date and reg_close_date < reg_open_date:
                await update.message.reply_text(
                    "❌ تاريخ إغلاق التسجيل يجب أن يكون بعد تاريخ الفتح.\n"
                    "Registration closing date must be after opening date.\n\n"
                    "Send /skip to skip."
                )
                return COURSE_REG_CLOSE_DATE
            
            # Validate: close date should be before course start
            end_date = context.user_data['new_course'].get('end_date')
            if end_date and reg_close_date > end_date:
                await update.message.reply_text(
                    "❌ يجب إغلاق التسجيل قبل أو في نهاية الكورس.\n"
                    "Registration must close close before or on the course end date.\n\n"
                    "Send /skip to skip."
                )
                return COURSE_REG_CLOSE_DATE
            
            context.user_data['new_course']['registration_close_date'] = reg_close_date
            await update.message.reply_text(f"✅ تاريخ إغلاق التسجيل: {date_text}")
        except ValueError:
            await update.message.reply_text(
                "❌ تنسيق غير صالح. استخدم YYYY-MM-DD\n"
                "Invalid format. Use YYYY-MM-DD\n\n"
                "Example: 2025-10-25\n\n"
                "Send /skip to skip."
            )
            return COURSE_REG_CLOSE_DATE
    
    # Show summary and ask for confirmation
    course_data = context.user_data['new_course']
    
    # Format dates for display
    start_date_str = course_data.get('start_date').strftime('%Y-%m-%d') if course_data.get('start_date') else 'لا يوجد / None'
    end_date_str = course_data.get('end_date').strftime('%Y-%m-%d') if course_data.get('end_date') else 'لا يوجد / None'
    reg_open_str = course_data.get('registration_open_date').strftime('%Y-%m-%d') if course_data.get('registration_open_date') else 'لا يوجد / None'
    reg_close_str = course_data.get('registration_close_date').strftime('%Y-%m-%d') if course_data.get('registration_close_date') else 'لا يوجد / None'
    
    summary = f"""
📋 **ملخص الكورس / Course Summary**

📌 **الاسم / Name:** {course_data['name']}

📝 **الوصف / Description:**
{course_data['description'][:200]}{'...' if len(course_data['description']) > 200 else ''}

💰 **السعر / Price:** {course_data['price']:.2f} SDG

🔗 **رابط المجموعة / Group Link:** {course_data.get('group_link') or 'لا يوجد / None'}

👥 **العدد الأقصى / Max Students:** {course_data.get('max_students') or 'غير محدود / Unlimited'}

📅 **تاريخ بداية الكورس / Course Start Date:** {start_date_str}

📅 **تاريخ نهاية الكورس / Course End Date:** {end_date_str}

🟢 **تاريخ فتح التسجيل / Registration Opens:** {reg_open_str}

🔴 **تاريخ إغلاق التسجيل / Registration Closes:** {reg_close_str}

هل تريد حفظ هذا الكورس؟
Do you want to save this course?
"""
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ نعم / Yes", callback_data="confirm_add_course"),
            InlineKeyboardButton("❌ لا / No", callback_data="cancel_add_course")
        ]
    ])
    
    await update.message.reply_text(summary, reply_markup=keyboard, parse_mode='Markdown')
    
    return COURSE_CONFIRM


async def course_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation of new course"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_add_course":
        await query.edit_message_text("❌ تم إلغاء إضافة الكورس.\nCourse addition cancelled.")
        context.user_data.pop('new_course', None)
        return ConversationHandler.END
    
    # Save course to database
    course_data = context.user_data['new_course']
    
    try:
        with get_db() as session:
            new_course = crud.create_course(
                session,
                course_name=course_data['name'],
                description=course_data['description'],
                price=course_data['price'],
                telegram_group_link=course_data.get('group_link'),
                max_students=course_data.get('max_students'),
                start_date=course_data.get('start_date'),
                end_date=course_data.get('end_date'),
                registration_open_date=course_data.get('registration_open_date'),
                registration_close_date=course_data.get('registration_close_date')
            )

            session.commit()
            
            logger.info(f"Admin {update.effective_user.id} created course: {new_course.course_id} - {new_course.course_name}")
            
            await query.edit_message_text(
                f"✅ **Course Created Successfully!**\n\n"
                f"📚 **{new_course.course_name}**\n"
                f"💰 Price: {new_course.price:.2f} SDG\n"
                f"🆔 Course ID: {new_course.course_id}\n\n"
                f"The course is now **active** and visible to students.",
                parse_mode='Markdown',
                reply_markup=back_to_main_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Failed to create course: {e}")
        await query.edit_message_text(
            f"❌ فشل في إضافة الكورس. حاول مرة أخرى.\n"
            f"Failed to add course. Please try again.\n\n"
            f"Error: {str(e)}"
        )
    
    context.user_data.pop('new_course', None)
    return ConversationHandler.END

async def cancel_course_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel course creation"""
    await update.message.reply_text(
        "❌ تم إلغاء العملية.\nOperation cancelled.",
        reply_markup=back_to_main_keyboard()
    )
    context.user_data.pop('new_course', None)
    return ConversationHandler.END

# ==================== /listcourses COMMAND ====================

async def list_courses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all courses with enrollment stats"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    with get_db() as session:
        courses = crud.get_all_courses(session)
        
        if not courses:
            await update.message.reply_text("📭 لا توجد كورسات.\nNo courses available.")
            return
        
        message = "📚 **قائمة الكورسات / Course List**\n\n"
        
        for course in courses:
            enrolled_count = len([e for e in course.enrollments if e.payment_status.value == 'VERIFIED'])
            max_students_str = str(course.max_students) if course.max_students else "∞"
            status = "🟢 مفعل / Active" if course.is_active else "🔴 متوقف / Inactive"
            
            message += f"""
🆔 **ID:** {course.course_id}
📌 **الاسم / Name:** {course.course_name}
💰 **السعر / Price:** {course.price:.2f} SDG
👥 **المسجلين / Enrolled:** {enrolled_count}/{max_students_str}
{status}
─────────────────
"""
        
        await update.message.reply_text(message, parse_mode='Markdown')

# ==================== /editcourse COMMAND ====================

async def edit_course_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start editing a course"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return ConversationHandler.END
    
    with get_db() as session:
        courses = crud.get_all_courses(session)
        
        if not courses:
            await update.message.reply_text("📭 لا توجد كورسات لتعديلها.\nNo courses to edit.")
            return ConversationHandler.END
        
        # Create buttons for each course
        keyboard = []
        for course in courses:
            keyboard.append([InlineKeyboardButton(
                f"{course.course_id} - {course.course_name}",
                callback_data=f"edit_course_{course.course_id}"
            )])
        
        keyboard.append([InlineKeyboardButton("❌ إلغاء / Cancel", callback_data="cancel_edit")])
        
        await update.message.reply_text(
            "📝 **تعديل كورس / Edit Course**\n\n"
            "اختر الكورس الذي تريد تعديله:\n"
            "Select the course you want to edit:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return EDIT_SELECT_COURSE

async def edit_select_course_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle course selection for editing"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_edit":
        await query.edit_message_text("❌ تم إلغاء التعديل.\nEdit cancelled.")
        return ConversationHandler.END
    
    course_id = int(query.data.split('_')[2])
    context.user_data['edit_course_id'] = course_id
    
    # Show fields that can be edited
    keyboard = [
        [InlineKeyboardButton("📝 الاسم / Name", callback_data="edit_field_name")],
        [InlineKeyboardButton("📄 الوصف / Description", callback_data="edit_field_description")],
        [InlineKeyboardButton("💰 السعر / Price", callback_data="edit_field_price")],
        [InlineKeyboardButton("🔗 رابط المجموعة / Group Link", callback_data="edit_field_group")],
        [InlineKeyboardButton("👥 العدد الأقصى / Max Students", callback_data="edit_field_max")],
        [InlineKeyboardButton("📅 تاريخ البداية / Start Date", callback_data="edit_field_start")],
        [InlineKeyboardButton("📅 تاريخ النهاية / End Date", callback_data="edit_field_end")],
        [InlineKeyboardButton("🟢 تاريخ فتح التسجيل / Reg Open", callback_data="edit_field_reg_open")],
        [InlineKeyboardButton("🔴 تاريخ إغلاق التسجيل / Reg Close", callback_data="edit_field_reg_close")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="edit_cancel")]
    ]

    
    await query.edit_message_text(
        f"✏️ **تعديل الكورس / Edit Course #{course_id}**\n\n"
        f"اختر الحقل الذي تريد تعديله:\n"
        f"Select the field you want to edit:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return EDIT_SELECT_FIELD

async def edit_select_field_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle field selection for editing"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_edit":
        await query.edit_message_text("❌ تم إلغاء التعديل.\nEdit cancelled.")
        context.user_data.pop('edit_course_id', None)
        return ConversationHandler.END
    
    field = '_'.join(query.data.split('_')[2:])
    context.user_data['edit_field'] = field
    
    field_names = {
        'name': 'اسم الدورة / Course Name',
        'description': 'وصف الدورة / Description',
        'price': 'السعر / Price',
        'group': 'رابط المجموعة / Group Link',
        'max': 'العدد الأقصى / Max Students',
        'start': 'تاريخ البداية / Start Date',
        'end': 'تاريخ النهاية / End Date',
        'reg_open': 'تاريخ فتح التسجيل / Registration Open Date',
        'reg_close': 'تاريخ إغلاق التسجيل / Registration Close Date'
    }
    
    await query.edit_message_text(
        f"✏️ **تعديل {field_names.get(field, field)}**\n\n"
        f"أدخل القيمة الجديدة:\n"
        f"Enter the new value:\n\n"
        f"Send /cancel to abort."
    )
    
    return EDIT_INPUT_VALUE

async def edit_input_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive new value for field"""
    new_value = update.message.text.strip()
    field = context.user_data.get('edit_field')
    course_id = context.user_data.get('edit_course_id')
    
    try:
        with get_db() as session:
            course = crud.get_course_by_id(session, course_id)
            
            if not course:
                await update.message.reply_text("❌ الكورس غير موجود.\nCourse not found.")
                return ConversationHandler.END
            
            # Update the appropriate field
            if field == 'name':
                course.course_name = new_value
                
            elif field == 'description':
                course.description = new_value
                
            elif field == 'price':
                course.price = float(new_value)
                
            elif field == 'group':
                course.telegram_group_link = new_value if new_value.lower() != 'none' else None
                
            elif field == 'max':
                max_val = int(new_value)
                course.max_students = max_val if max_val > 0 else None
                
            elif field == 'start':
                from datetime import datetime
                if new_value.lower() in ['none', 'skip', '/skip']:
                    course.start_date = None
                else:
                    course.start_date = datetime.strptime(new_value, '%Y-%m-%d')
                    
            elif field == 'end':
                from datetime import datetime
                if new_value.lower() in ['none', 'skip', '/skip']:
                    course.end_date = None
                else:
                    end_date = datetime.strptime(new_value, '%Y-%m-%d')
                    # Validate: end date should be after start date if both exist
                    if course.start_date and end_date < course.start_date:
                        await update.message.reply_text(
                            "❌ تاريخ النهاية يجب أن يكون بعد تاريخ البداية.\n"
                            "End date must be after start date."
                        )
                        return ConversationHandler.END
                    course.end_date = end_date
                    
            elif field == 'reg_open':
                from datetime import datetime
                if new_value.lower() in ['none', 'skip', '/skip']:
                    course.registration_open_date = None
                else:
                    try:
                        course.registration_open_date = datetime.strptime(new_value, '%Y-%m-%d')
                    except ValueError:
                        await update.message.reply_text(
                            "❌ تنسيق غير صالح. استخدم YYYY-MM-DD\n"
                            "Invalid format. Use YYYY-MM-DD\n\n"
                            "Example: 2025-12-31"
                        )
                        return ConversationHandler.END
                        
            elif field == 'reg_close':
                from datetime import datetime
                if new_value.lower() in ['none', 'skip', '/skip']:
                    course.registration_close_date = None
                else:
                    try:
                        reg_close = datetime.strptime(new_value, '%Y-%m-%d')
                        # Validate: close date should be after open date
                        if course.registration_open_date and reg_close < course.registration_open_date:
                            await update.message.reply_text(
                                "❌ تاريخ الإغلاق يجب أن يكون بعد تاريخ الفتح.\n"
                                "Registration closing date must be after opening date."
                            )
                            return ConversationHandler.END
                        # Validate: close date should not be after course end
                        if course.end_date and reg_close > course.end_date:
                            await update.message.reply_text(
                                "❌ يجب إغلاق التسجيل قبل أو في نهاية الكورس.\n"
                                "Registration must close before or on the course end date."
                            )
                            return ConversationHandler.END
                        course.registration_close_date = reg_close
                    except ValueError:
                        await update.message.reply_text(
                            "❌ تنسيق غير صالح. استخدم YYYY-MM-DD\n"
                            "Invalid format. Use YYYY-MM-DD\n\n"
                            "Example: 2025-12-31"
                        )
                        return ConversationHandler.END
            
            # ✅ COMMIT THE CHANGES
            session.commit()
            session.refresh(course)  # Refresh to get updated values
            
            logger.info(f"Admin {update.effective_user.id} edited course {course_id}: {field} = {new_value}")
            
            await update.message.reply_text(
                f"✅ تم تحديث الكورس بنجاح!\n"
                f"✅ Course Updated Successfully!\n\n"
                f"🆔 Course ID: {course_id}\n"
                f"Updated field: {field.replace('_', ' ')}\n"
                f"New value: {new_value}"
            )
            
    except Exception as e:
        logger.error(f"Failed to update course: {e}")
        await update.message.reply_text(f"❌ فشل التحديث.\nUpdate failed.\n\nError: {str(e)}")
    
    context.user_data.pop('edit_course_id', None)
    context.user_data.pop('edit_field', None)
    return ConversationHandler.END


# ==================== /deletecourse COMMAND ====================

async def delete_course_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a course (with safety checks)"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    with get_db() as session:
        courses = crud.get_all_courses(session)
        
        if not courses:
            await update.message.reply_text("📭 لا توجد كورسات للحذف.\nNo courses to delete.")
            return
        
        keyboard = []
        for course in courses:
            enrolled_count = len([e for e in course.enrollments if e.payment_status.value == 'VERIFIED'])
            keyboard.append([InlineKeyboardButton(
                f"{course.course_id} - {course.course_name} ({enrolled_count} students)",
                callback_data=f"delete_course_{course.course_id}"
            )])
        
        keyboard.append([InlineKeyboardButton("❌ إلغاء / Cancel", callback_data="cancel_delete")])
        
        await update.message.reply_text(
            "⚠️ **حذف كورس / Delete Course**\n\n"
            "⚠️ تحذير: هذا الإجراء لا يمكن التراجع عنه!\n"
            "Warning: This action cannot be undone!\n\n"
            "اختر الكورس الذي تريد حذفه:\n"
            "Select the course you want to delete:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def delete_course_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle course deletion"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_delete":
        await query.edit_message_text("❌ تم إلغاء الحذف.\nDeletion cancelled.")
        return
    
    course_id = int(query.data.split('_')[2])
    
    with get_db() as session:
        course = crud.get_course_by_id(session, course_id)
        
        if not course:
            await query.edit_message_text("❌ الكورس غير موجود.\nCourse not found.")
            return
        
        # Check if course has enrolled students
        verified_enrollments = [e for e in course.enrollments if e.payment_status.value == 'VERIFIED']
        
        if verified_enrollments:
            await query.edit_message_text(
                f"⚠️ **لا يمكن الحذف!**\n"
                f"Cannot Delete!\n\n"
                f"هذا الكورس يحتوي على {len(verified_enrollments)} طالب مسجل.\n"
                f"This course has {len(verified_enrollments)} enrolled students.\n\n"
                f"استخدم /togglecourse لتعطيل الكورس بدلاً من حذفه.\n"
                f"Use /togglecourse to deactivate instead of deleting.",
                parse_mode='Markdown'
            )
            return
        
        # Delete course
        try:
            course_name = course.course_name  # Save before deleting
            session.delete(course)
            session.commit()
            
            logger.info(f"Admin {update.effective_user.id} deleted course {course_id}: {course_name}")
            
            await query.edit_message_text(
                f"✅ **تم حذف الكورس بنجاح!**\n"
                f"Deleted: {course_name}",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Failed to delete course: {e}")
            await query.edit_message_text(f"❌ فشل الحذف.\nDeletion failed.\n\nError: {str(e)}")

# ==================== /togglecourse COMMAND ====================

async def toggle_course_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle course active status"""
    user = update.effective_user
    
    if not is_admin_user(user.id):
        await update.message.reply_text("❌ Admin access only.")
        return
    
    with get_db() as session:
        courses = crud.get_all_courses(session)
        
        if not courses:
            await update.message.reply_text("📭 لا توجد كورسات.\nNo courses available.")
            return
        
        keyboard = []
        for course in courses:
            status_emoji = "🟢" if course.is_active else "🔴"
            keyboard.append([InlineKeyboardButton(
                f"{status_emoji} {course.course_id} - {course.course_name}",
                callback_data=f"toggle_course_{course.course_id}"
            )])
        
        keyboard.append([InlineKeyboardButton("❌ إلغاء / Cancel", callback_data="cancel_toggle")])
        
        await update.message.reply_text(
            "🔄 **تفعيل/تعطيل كورس / Toggle Course**\n\n"
            "اختر الكورس:\n"
            "Select course:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def toggle_course_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle course toggle"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_toggle":
        await query.edit_message_text("❌ تم الإلغاء.\nCancelled.")
        return
    
    course_id = int(query.data.split('_')[2])
    
    with get_db() as session:
        course = crud.get_course_by_id(session, course_id)
        
        if not course:
            await query.edit_message_text("❌ الكورس غير موجود.\nCourse not found.")
            return
        
        # Toggle status
        course.is_active = not course.is_active
        session.commit()
        
        status = "مفعل / Active" if course.is_active else "متوقف / Inactive"
        emoji = "🟢" if course.is_active else "🔴"
        
        logger.info(f"Admin {update.effective_user.id} toggled course {course_id} to {status}")
        
        await query.edit_message_text(
            f"✅ **تم التحديث!**\n\n"
            f"{emoji} الكورس الآن: {status}\n"
            f"Course is now: {status}\n\n"
            f"📌 {course.course_name}",
            parse_mode='Markdown'
        )
