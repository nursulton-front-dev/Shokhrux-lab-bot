import datetime
import os
from aiogram import Router, Bot, F
from aiogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.database.models import User, Subscription, Payment
from bot.states.registration import RegistrationStates
from bot.config import config
from bot.services.rahmat import generate_invoice_link

router = Router()

def get_channel_id() -> int:
    return config.channel_id or int(os.getenv("CHANNEL_ID", "-1001234567890"))

TARIFFS = {
    "1": {"months": 1, "price": 500000, "days": 30},
    "3": {"months": 3, "price": 1200000, "days": 90},
    "6": {"months": 6, "price": 2300000, "days": 180}
}

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Mening profilim"), KeyboardButton(text="🚀 Obuna bo'lish")],
            [KeyboardButton(text="💬 Yordam")]
        ],
        resize_keyboard=True
    )

@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    # Ensure user is recorded in the database
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name
        )
        session.add(user)
        await session.commit()
    
    welcome_text = (
        "🌟 <b>Arzanda qomat va sog'lom hayot sari xush kelibsiz!</b>\n\n"
        "Siz shunchaki kanalga emas, balki haqiqiy natijalarga erishishingizga yordam beruvchi yopiq fitnes-klubga taklifnoma oldingiz!\n\n"
        "Bu yerda internetdagi quruq va foydasiz maslahatlar emas, balki aniq ishlaydigan tizimni qo'lga kiritasiz:\n\n"
        "🏋️‍♂️ <b>Yopiq kanalimizda sizni nimalar kutmoqda?</b>\n\n"
        "• Ozish va mushak massasini yig'ish uchun samarali mashg'ulot dasturlari\n\n"
        "• Ortikcha vazndan xalos bo'lish uchun shaxsiy va mazali taomnoma (PP-retseptlar)\n\n"
        "• Moddalar almashinuvini tezlashtirish hamda natijani saqlab qolish sirlari\n\n"
        "• Sizni to'xtab qolishga yo'l qo'ymaydigan kuchli motivatsiya va hamjamiyat\n\n"
        "🔥 Ortiqcha vazndan xalos bo'lib, o'zingizning eng yaxshi versiyangizni kashf etish vaqti keldi!\n\n"
        "O'zingizga mos tarifni tanlang va hoziroq safimizga qo'shiling 👇"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=main_menu_keyboard()
    )
    await show_tariffs(message)

@router.message(F.text == "💬 Yordam")
async def msg_support(message: Message):
    if config.support_username:
        await message.answer(f"Savollaringiz bo'lsa, yordamchi administrator bilan bog'laning: @{config.support_username}")
    else:
        await message.answer("Qo'llab-quvvatlash markazi bilan bog'lanish uchun adminimizga yozing.")

@router.message(Command("profile"))
@router.message(F.text == "👤 Mening profilim")
async def msg_profile(message: Message, session: AsyncSession):
    user_id = message.from_user.id
    
    stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.status == "active"
    ).order_by(Subscription.expires_at.desc()).limit(1)
    
    result = await session.execute(stmt)
    current_sub = result.scalar_one_or_none()
    
    now = datetime.datetime.now(datetime.timezone.utc)
    
    if current_sub and current_sub.expires_at > now:
        status_emoji = "✅"
        status_text = "FAOL"
        expires_at_str = current_sub.expires_at.strftime("%Y-%m-%d %H:%M")
    else:
        status_emoji = "❌"
        status_text = "MUDDATI TUGAGAN (yoki yo'q)"
        expires_at_str = "-"
        
    text = (
        f"👤 <b>Sizning profilingiz</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n\n"
        f"📊 Status: {status_emoji} {status_text}\n\n"
        f"⏳ Obuna tugash sanasi: {expires_at_str}\n\n"
        f"💡 Obunangiz muddatini istalgan vaqtda uzaytirishingiz mumkin."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Obunani uzaytirish / Xarid", callback_data="start_sub")]
    ])
    
    await message.answer(text, reply_markup=kb)

@router.message(F.text == "🚀 Obuna bo'lish")
async def msg_subscribe(message: Message, session: AsyncSession, state: FSMContext):
    await check_registration_and_show_tariffs(message.from_user.id, message, session, state)

@router.callback_query(F.data == "start_sub")
async def cb_start_sub(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await check_registration_and_show_tariffs(callback.from_user.id, callback.message, session, state)
    await callback.answer()

async def check_registration_and_show_tariffs(user_id: int, message_obj: Message, session: AsyncSession, state: FSMContext):
    stmt = select(User).where(User.telegram_id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not user.full_name or not user.phone_number:
        await message_obj.answer("Obunani rasmiylashtirish uchun, iltimos, Ismingiz va Familiyangizni kiriting:")
        await state.set_state(RegistrationStates.waiting_for_name)
    else:
        await show_tariffs(message_obj)

@router.message(RegistrationStates.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await message.answer("Aktivatsiya qilish uchun telefon raqamingizni yuboring:", reply_markup=kb)
    await state.set_state(RegistrationStates.waiting_for_phone)

@router.message(RegistrationStates.waiting_for_phone, F.contact)
async def process_phone(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    full_name = data.get("full_name")
    phone_number = message.contact.phone_number
    
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user:
        user.full_name = full_name
        user.phone_number = phone_number
        await session.commit()
    
    await message.answer("✅ Ma'lumotlaringiz muvaffaqiyatli saqlandi!", reply_markup=main_menu_keyboard())
    await state.clear()
    
    await show_tariffs(message)

async def show_tariffs(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Oylik — 500,000 UZS", callback_data="tariff_1")],
        [InlineKeyboardButton(text="3 Oylik — 1,200,000 UZS", callback_data="tariff_3")],
        [InlineKeyboardButton(text="6 Oylik — 2,300,000 UZS", callback_data="tariff_6")]
    ])
    await message.answer("O'zingizga mos tarifni tanlang:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("tariff_"))
async def cb_tariff_selected(callback: CallbackQuery, session: AsyncSession):
    tariff_months = callback.data.split("_")[1]
    tariff = TARIFFS[tariff_months]
    
    # Calculate expiry date
    user_id = callback.from_user.id
    sub_stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.status == "active"
    ).order_by(Subscription.expires_at.desc()).limit(1)
    
    result = await session.execute(sub_stmt)
    current_sub = result.scalar_one_or_none()
    now = datetime.datetime.now(datetime.timezone.utc)
    if current_sub and current_sub.expires_at > now:
        expires_at = current_sub.expires_at + datetime.timedelta(days=tariff['days'])
    else:
        expires_at = now + datetime.timedelta(days=tariff['days'])
        
    expiry_date_str = expires_at.strftime("%Y-%m-%d %H:%M UTC")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 To'lov qilish", callback_data=f"pay_manual_{tariff_months}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="start_sub")]
    ])
    
    text = (
        f"💳 <b>{tariff_months} oylik tarifi tanlandi</b>\n\n"
        f"💰 To'lov miqdori: <b>{tariff['price']:,} UZS</b>\n\n"
        f"⏳ Obuna tugash sanasi: <b>{expiry_date_str}</b>\n\n"
        f"⚡️ <b>To'lov usullari:</b>\n\n"
        f"Payme, Click, Uzum Bank yoki bank kartalari (Uzcard / Humo) orqali bir zumda to'lashingiz mumkin.\n\n"
        f"To'lovni amalga oshirish uchun pastdagi «To'lov qilish» tugmasini bosing.\n\n"
        f"To'lov tasdiqlanishi bilan bot sizga avtomatik ravishda yopiq fitnes-kanalga bir marta ishlatiladigan taklifnoma havolasini yuboradi!"
    )
            
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("pay_manual_"))
async def cb_pay_manual(callback: CallbackQuery):
    tariff_months = callback.data.split("_")[2]
    tariff = TARIFFS[tariff_months]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ To'lov qildim", callback_data=f"mock_pay_success_{tariff_months}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"tariff_{tariff_months}")]
    ])
    
    text = (f"⚠️ <b>Qo'lda to'lov qilish:</b>\n\n"
            f"Iltimos, {tariff['price']:,} UZS summani quyidagi kartaga o'tkazing:\n"
            f"💳 <code>8600 0000 0000 0000</code>\n"
            f"👤 Qabul qiluvchi: Ism F.\n\n"
            f"To'lovni amalga oshirgach, <b>«To'lov qildim»</b> tugmasini bosing.")
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("mock_pay_success_"))
async def cb_mock_pay(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    tariff_months = callback.data.split("_")[3]
    tariff = TARIFFS[tariff_months]
    user_id = callback.from_user.id
    
    # 1. Record the Payment
    payment = Payment(
        user_id=user_id,
        amount=tariff['price'],
        tariff_months=int(tariff_months),
        status="pending"
    )
    session.add(payment)
    await session.flush()
    
    # 2. Notify Admins for manual confirmation
    admin_ids = config.get_admin_ids
    if admin_ids:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_conf_{payment.id}_{user_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"admin_rej_{payment.id}_{user_id}")
            ]
        ])
        admin_text = (f"🆕 <b>Yangi to'lov arizasi!</b>\n\n"
                      f"Foydalanuvchi: <a href='tg://user?id={user_id}'>{callback.from_user.full_name or 'Foydalanuvchi'}</a>\n"
                      f"Tarif: {tariff_months} oylik\n"
                      f"Summa: {tariff['price']:,} UZS\n\n"
                      f"Mablag' tushganligini tasdiqlang.")
        
        for a_id in admin_ids:
            try:
                await bot.send_message(chat_id=a_id, text=admin_text, reply_markup=admin_kb)
            except Exception as e:
                print(f"Error notifying admin {a_id}: {e}")

    success_text = (
        f"⏳ <b>Sizning arizangiz adminga yuborildi!</b>\n\n"
        f"Admin to'lovingizni tasdiqlashi bilan sizga kanalga kirish uchun maxsus havola yuboriladi.\n"
        f"Iltimos, kuting..."
    )
    await callback.message.edit_text(success_text)
    await session.commit()
    await callback.answer()
