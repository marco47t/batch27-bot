"""
Admin handlers for instructor management
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import crud, get_db
from utils.keyboards import back_to_main_keyboard
import logging

logger = logging.getLogger(__name__)

# Conversation states
(INSTRUCTOR_NAME, INSTRUCTOR_BIO, INSTRUCTOR_SPECIALIZATION, 
 INSTRUCTOR_EMAIL, INSTRUCTOR_PHONE) = range(5)


async def manage_instructors_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show instructor management menu"""
    query = update.callback_query
    if query:
        await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة مدرب جديد | Add Instructor", callback_data="admin_add_instructor")],
        [InlineKeyboardButton("📋 عرض المدربين | View Instructors", callback_data="admin_view_instructors")],
        [InlineKeyboardButton("🔙 عودة | Back", callback_data="admin_menu")]
    ]
    
    message = """👨‍🏫 **إدارة المدربين**
**Instructor Management**
━━━━━━━━━━━━━━━━━━━━

اختر خياراً:
Choose an option:"""
    
    if query:
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def view_instructors_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of all instructors"""
    query = update.callback_query
    await query.answer()
    
    with get_db() as session:
        instructors = crud.get_all_instructors(session, active_only=False)
        
        if not instructors:
            await query.edit_message_text(
                "لا يوجد مدربين مسجلين\nNo instructors registered",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 عودة | Back", callback_data="admin_manage_instructors")
                ]])
            )
            return
        
        message = "👨‍🏫 **قائمة المدربين**\n**Instructors List**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        
        keyboard = []
        for instructor in instructors:
            status = "✅" if instructor.is_active else "❌"
            avg_rating = crud.get_instructor_average_rating(session, instructor.instructor_id)
            rating_text = f" ({avg_rating}⭐)" if avg_rating else ""
            
            message += f"{status} **{instructor.name}**{rating_text}\n"
            message += f"   📚 {instructor.specialization or 'غير محدد'}\n\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"✏️ {instructor.name}", 
                    callback_data=f"admin_edit_instructor_{instructor.instructor_id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 عودة | Back", callback_data="admin_manage_instructors")])
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


async def start_add_instructor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding new instructor"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "➕ **إضافة مدرب جديد**\n\n"
        "أدخل اسم المدرب:\n"
        "Enter instructor name:",
        parse_mode='Markdown'
    )
    
    return INSTRUCTOR_NAME


async def receive_instructor_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive instructor name"""
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text("❌ الاسم قصير جداً. حاول مرة أخرى:")
        return INSTRUCTOR_NAME
    
    context.user_data['new_instructor'] = {'name': name}
    
    await update.message.reply_text(
        f"✅ الاسم: {name}\n\n"
        "أدخل التخصص (مثال: برمجة، تصميم، إدارة):\n"
        "Enter specialization (e.g., Programming, Design, Management):"
    )
    
    return INSTRUCTOR_SPECIALIZATION


async def receive_instructor_specialization(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive instructor specialization"""
    specialization = update.message.text.strip()
    
    context.user_data['new_instructor']['specialization'] = specialization
    
    await update.message.reply_text(
        f"✅ التخصص: {specialization}\n\n"
        "أدخل السيرة الذاتية (نبذة عن المدرب):\n"
        "Enter bio (about the instructor):"
    )
    
    return INSTRUCTOR_BIO


async def receive_instructor_bio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive instructor bio"""
    bio = update.message.text.strip()
    
    context.user_data['new_instructor']['bio'] = bio
    
    await update.message.reply_text(
        f"✅ السيرة الذاتية محفوظة\n\n"
        "أدخل البريد الإلكتروني (أو /skip للتخطي):\n"
        "Enter email (or /skip):"
    )
    
    return INSTRUCTOR_EMAIL


async def receive_instructor_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive instructor email"""
    email = update.message.text.strip()
    
    if email != "/skip":
        context.user_data['new_instructor']['email'] = email
    
    await update.message.reply_text(
        "أدخل رقم الهاتف (أو /skip للتخطي):\n"
        "Enter phone number (or /skip):"
    )
    
    return INSTRUCTOR_PHONE


async def receive_instructor_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive instructor phone and save to database"""
    phone = update.message.text.strip()
    
    if phone != "/skip":
        context.user_data['new_instructor']['phone'] = phone
    
    instructor_data = context.user_data.pop('new_instructor')
    
    # Save to database
    with get_db() as session:
        instructor = crud.create_instructor(
            session,
            name=instructor_data['name'],
            bio=instructor_data.get('bio'),
            specialization=instructor_data.get('specialization'),
            email=instructor_data.get('email'),
            phone=instructor_data.get('phone')
        )
        
        await update.message.reply_text(
            f"✅ **تم إضافة المدرب بنجاح!**\n\n"
            f"👨‍🏫 الاسم: {instructor.name}\n"
            f"📚 التخصص: {instructor.specialization or 'غير محدد'}\n"
            f"📧 البريد: {instructor.email or 'غير محدد'}\n"
            f"📞 الهاتف: {instructor.phone or 'غير محدد'}\n\n"
            f"✅ **Instructor Added Successfully!**",
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END


async def cancel_add_instructor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel adding instructor"""
    await update.message.reply_text("❌ تم إلغاء إضافة المدرب")
    context.user_data.pop('new_instructor', None)
    return ConversationHandler.END


async def edit_instructor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show instructor details for editing"""
    query = update.callback_query
    await query.answer()
    
    instructor_id = int(query.data.split('_')[-1])
    
    with get_db() as session:
        instructor = crud.get_instructor_by_id(session, instructor_id)
        
        if not instructor:
            await query.edit_message_text("❌ المدرب غير موجود")
            return
        
        avg_rating = crud.get_instructor_average_rating(session, instructor_id)
        review_count = len(crud.get_instructor_reviews(session, instructor_id))
        courses = crud.get_instructor_courses(session, instructor_id)
        
        rating_text = f"{avg_rating}⭐ ({review_count} تقييم)" if avg_rating else "لا توجد تقييمات"
        
        message = f"""👨‍🏫 **{instructor.name}**
━━━━━━━━━━━━━━━━━━━━

📚 التخصص: {instructor.specialization or 'غير محدد'}
⭐ التقييم: {rating_text}
📧 البريد: {instructor.email or 'غير محدد'}
📞 الهاتف: {instructor.phone or 'غير محدد'}
📝 الحالة: {"نشط ✅" if instructor.is_active else "غير نشط ❌"}

**عدد الدورات:** {len(courses)}

**السيرة الذاتية:**
{instructor.bio or 'لا توجد سيرة ذاتية'}
"""
        
        keyboard = [
            [InlineKeyboardButton(
                "🔴 تعطيل | Deactivate" if instructor.is_active else "🟢 تفعيل | Activate",
                callback_data=f"admin_toggle_instructor_{instructor_id}"
            )],
            [InlineKeyboardButton("🔙 عودة | Back", callback_data="admin_view_instructors")]
        ]
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


async def toggle_instructor_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle instructor active status"""
    query = update.callback_query
    await query.answer()
    
    instructor_id = int(query.data.split('_')[-1])
    
    with get_db() as session:
        instructor = crud.get_instructor_by_id(session, instructor_id)
        
        if not instructor:
            await query.edit_message_text("❌ المدرب غير موجود")
            return
        
        # Toggle status
        new_status = not instructor.is_active
        crud.update_instructor(session, instructor_id, is_active=new_status)
        
        status_text = "تم التفعيل ✅" if new_status else "تم التعطيل ❌"
        
        await query.answer(status_text)
        
        # Show updated details
        await edit_instructor_callback(update, context)
