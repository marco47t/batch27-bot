"""
Handler for collecting user legal names (4 parts)
"""

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters
)
from database import crud, get_db
from utils.helpers import handle_error
import logging

logger = logging.getLogger(__name__)

# Conversation states
FIRST_NAME, FATHER_NAME, GRANDFATHER_NAME, GREAT_GRANDFATHER_NAME = range(4)


async def start_legal_name_collection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start collecting legal name"""
    user = update.effective_user
    db = next(get_db())
    
    try:
        # Get or create user
        db_user = crud.get_or_create_user(
            db, 
            user.id, 
            user.username, 
            user.first_name, 
            user.last_name
        )
        
        # Check if already has legal name
        if crud.has_legal_name(db, db_user.user_id):
            legal_name = crud.get_user_legal_name(db, db_user.user_id)
            await update.message.reply_text(
                f"✅ لديك اسم قانوني مسجل بالفعل:\n{legal_name}\n\n"
                f"✅ You already have a legal name registered:\n{legal_name}\n\n"
                "إذا كنت تريد تحديثه، استخدم الأمر /update_legal_name\n"
                "If you want to update it, use /update_legal_name"
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            "📝 *تسجيل الاسم القانوني | Legal Name Registration*\n\n"
            "يرجى إدخال اسمك الرباعي الكامل كما هو مكتوب في المستندات الرسمية.\n"
            "Please enter your full four-part name as written on official documents.\n\n"
            "⚠️ *مهم جداً:*\n"
            "• يجب أن يكون الاسم باللغة الإنجليزية\n"
            "• الاسم الرباعي: (اسمك - اسم والدك - اسم جدك - اسم جد والدك)\n\n"
            "⚠️ *Very Important:*\n"
            "• Name must be in English\n"
            "• Four parts: (Your name - Father's name - Grandfather's name - Great-grandfather's name)\n\n"
            "🔹 *الخطوة 1/4:* أدخل اسمك الأول\n"
            "🔹 *Step 1/4:* Enter your first name",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        
        return FIRST_NAME
        
    except Exception as e:
        await handle_error(update, context, e)
        return ConversationHandler.END
    finally:
        db.close()


async def receive_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive first name"""
    # Exit early if user_data is not available (e.g., in a channel)
    if not context.user_data:
        return ConversationHandler.END
        
    first_name = update.message.text.strip()
    
    # Validate English only
    if not first_name.replace(' ', '').isalpha() or not first_name.isascii():
        await update.message.reply_text(
            "❌ يجب أن يكون الاسم باللغة الإنجليزية فقط\n"
            "❌ Name must be in English only\n\n"
            "🔹 *الخطوة 1/4:* أدخل اسمك الأول\n"
            "🔹 *Step 1/4:* Enter your first name",
            parse_mode='Markdown'
        )
        return FIRST_NAME
    
    # Store in context
    context.user_data['legal_name_first'] = first_name
    
    await update.message.reply_text(
        f"✅ تم حفظ: {first_name}\n\n"
        "🔹 *الخطوة 2/4:* أدخل اسم والدك\n"
        "🔹 *Step 2/4:* Enter your father's name",
        parse_mode='Markdown'
    )
    
    return FATHER_NAME


async def receive_father_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive father's name"""
    # Exit early if user_data is not available (e.g., in a channel)
    if not context.user_data:
        return ConversationHandler.END
        
    father_name = update.message.text.strip()
    
    # Validate English only
    if not father_name.replace(' ', '').isalpha() or not father_name.isascii():
        await update.message.reply_text(
            "❌ يجب أن يكون الاسم باللغة الإنجليزية فقط\n"
            "❌ Name must be in English only\n\n"
            "🔹 *الخطوة 2/4:* أدخل اسم والدك\n"
            "🔹 *Step 2/4:* Enter your father's name",
            parse_mode='Markdown'
        )
        return FATHER_NAME
    
    # Store in context
    context.user_data['legal_name_father'] = father_name
    
    await update.message.reply_text(
        f"✅ تم حفظ: {father_name}\n\n"
        "🔹 *الخطوة 3/4:* أدخل اسم جدك\n"
        "🔹 *Step 3/4:* Enter your grandfather's name",
        parse_mode='Markdown'
    )
    
    return GRANDFATHER_NAME


async def receive_grandfather_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive grandfather's name"""
    # Exit early if user_data is not available (e.g., in a channel)
    if not context.user_data:
        return ConversationHandler.END
        
    grandfather_name = update.message.text.strip()
    
    # Validate English only
    if not grandfather_name.replace(' ', '').isalpha() or not grandfather_name.isascii():
        await update.message.reply_text(
            "❌ يجب أن يكون الاسم باللغة الإنجليزية فقط\n"
            "❌ Name must be in English only\n\n"
            "🔹 *الخطوة 3/4:* أدخل اسم جدك\n"
            "🔹 *Step 3/4:* Enter your grandfather's name",
            parse_mode='Markdown'
        )
        return GRANDFATHER_NAME
    
    # Store in context
    context.user_data['legal_name_grandfather'] = grandfather_name
    
    await update.message.reply_text(
        f"✅ تم حفظ: {grandfather_name}\n\n"
        "🔹 *الخطوة 4/4:* أدخل اسم جد والدك\n"
        "🔹 *Step 4/4:* Enter your great-grandfather's name",
        parse_mode='Markdown'
    )
    
    return GREAT_GRANDFATHER_NAME


async def receive_great_grandfather_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive great-grandfather's name and save all"""
    # Exit early if user_data is not available (e.g., in a channel)
    if not context.user_data:
        return ConversationHandler.END
        
    great_grandfather_name = update.message.text.strip()
    user = update.effective_user
    db = next(get_db())
    
    try:
        # Validate English only
        if not great_grandfather_name.replace(' ', '').isalpha() or not great_grandfather_name.isascii():
            await update.message.reply_text(
                "❌ يجب أن يكون الاسم باللغة الإنجليزية فقط\n"
                "❌ Name must be in English only\n\n"
                "🔹 *الخطوة 4/4:* أدخل اسم جد والدك\n"
                "🔹 *Step 4/4:* Enter your great-grandfather's name",
                parse_mode='Markdown'
            )
            return GREAT_GRANDFATHER_NAME
        
        # Get user from database
        db_user = crud.get_or_create_user(
            db, 
            user.id, 
            user.username, 
            user.first_name, 
            user.last_name
        )
        
        # Save legal name
        success = crud.update_user_legal_name(
            db,
            db_user.user_id,
            context.user_data['legal_name_first'],
            context.user_data['legal_name_father'],
            context.user_data['legal_name_grandfather'],
            great_grandfather_name
        )
        
        if success:
            full_name = (
                f"{context.user_data['legal_name_first']} "
                f"{context.user_data['legal_name_father']} "
                f"{context.user_data['legal_name_grandfather']} "
                f"{great_grandfather_name}"
            )
            
            await update.message.reply_text(
                "✅ *تم حفظ اسمك القانوني بنجاح!*\n"
                "✅ *Legal name saved successfully!*\n\n"
                f"📋 *الاسم الكامل | Full Name:*\n{full_name}\n\n"
                "يمكنك الآن متابعة استخدام البوت.\n"
                "You can now continue using the bot.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ حدث خطأ أثناء حفظ الاسم. يرجى المحاولة مرة أخرى.\n"
                "❌ Error saving name. Please try again."
            )
        
        # Clear user data
        context.user_data.clear()
        
        return ConversationHandler.END
        
    except Exception as e:
        await handle_error(update, context, e)
        context.user_data.clear()
        return ConversationHandler.END
    finally:
        db.close()


async def cancel_legal_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel legal name collection"""
    # Exit early if user_data is not available (e.g., in a channel)
    if not context.user_data:
        return ConversationHandler.END
        
    context.user_data.clear()
    
    await update.message.reply_text(
        "❌ تم إلغاء عملية تسجيل الاسم القانوني\n"
        "❌ Legal name registration cancelled",
        reply_markup=ReplyKeyboardRemove()
    )
    
    return ConversationHandler.END


# Conversation handler
legal_name_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("set_legal_name", start_legal_name_collection),
        CommandHandler("update_legal_name", start_legal_name_collection)
    ],
    states={
        FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_first_name)],
        FATHER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_father_name)],
        GRANDFATHER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_grandfather_name)],
        GREAT_GRANDFATHER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_great_grandfather_name)],
    },
    fallbacks=[CommandHandler("cancel", cancel_legal_name)],
    name="legal_name_conversation",
    persistent=False
)
