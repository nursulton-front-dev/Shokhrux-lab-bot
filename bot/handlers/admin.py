from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from bot.database.models import User, Subscription, Payment
from bot.filters.admin import IsAdmin
from bot.config import config

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

@router.message(Command("admin"))
@router.message(CommandStart())
async def cmd_admin(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar ro'yxati", callback_data="admin_users")],
        [InlineKeyboardButton(text="⏳ Kutilayotgan to'lovlar", callback_data="admin_pending_payments")],
    ])
    await message.answer("👑 <b>Admin Paneli</b>\n\nKerakli amalni tanlang:", reply_markup=keyboard)

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery, session: AsyncSession):
    # Fetch counts
    users_count = await session.scalar(select(func.count()).select_from(User))
    active_subs = await session.scalar(select(func.count()).where(Subscription.status == 'active').select_from(Subscription))
    expired_subs = await session.scalar(select(func.count()).where(Subscription.status == 'expired').select_from(Subscription))
    
    total_revenue_res = await session.scalar(select(func.sum(Payment.amount)).where(Payment.status == 'completed'))
    total_revenue = total_revenue_res or 0
    
    pending_payments = await session.scalar(select(func.count()).where(Payment.status == 'pending').select_from(Payment))

    text = (
        f"📊 <b>Loyiha statistikasi:</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{users_count}</b>\n"
        f"✅ Faol obunalar: <b>{active_subs}</b>\n"
        f"❌ Muddati tugagan obunalar: <b>{expired_subs}</b>\n"
        f"⏳ Kutilayotgan to'lov arizalari: <b>{pending_payments}</b>\n\n"
        f"💰 Taxminiy daromad: <b>{total_revenue:,} UZS</b>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "admin_main")
async def cb_admin_main(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar ro'yxati", callback_data="admin_users")],
        [InlineKeyboardButton(text="⏳ Kutilayotgan to'lovlar", callback_data="admin_pending_payments")],
    ])
    await callback.message.edit_text("👑 <b>Admin Paneli</b>\n\nKerakli amalni tanlang:", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery, session: AsyncSession):
    stmt = select(User).limit(10)
    result = await session.execute(stmt)
    users = result.scalars().all()
    
    if not users:
        await callback.answer("Foydalanuvchilar topilmadi.", show_alert=True)
        return
        
    text = "👥 <b>So'nggi 10 ta foydalanuvchi:</b>\n\n"
    for u in users:
        text += f"ID: <code>{u.telegram_id}</code> | Ism: {u.full_name or 'Yoq'} | @{u.username or 'Yoq'}\n"
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "admin_pending_payments")
async def cb_admin_pending_payments(callback: CallbackQuery, session: AsyncSession):
    stmt = select(Payment).where(Payment.status == "pending").limit(5)
    result = await session.execute(stmt)
    payments = result.scalars().all()
    
    if not payments:
        await callback.message.edit_text(
            "✅ Kutilayotgan arizalar yo'q.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main")]
            ])
        )
        return

    text = "⏳ <b>Kutilayotgan arizalar:</b>\n(Tasdiqlash uchun shaxsiy xabarlardagi tugmalardan foydalaning)\n\n"
    for p in payments:
        text += f"Ariza ID: <b>{p.id}</b> | Summa: {p.amount:,} UZS | User ID: <code>{p.user_id}</code>\n"
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
