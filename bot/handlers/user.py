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
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.database.models import User, Subscription, Payment
from bot.states.registration import RegistrationStates
from bot.config import config

router = Router()

def get_channel_id() -> int:
    return config.channel_id or int(os.getenv("CHANNEL_ID", "-1001234567890"))

TARIFFS = {
    "1": {"months": 1, "price": 500000, "days": 30},
    "3": {"months": 3, "price": 1200000, "days": 90},
    "6": {"months": 6, "price": 2300000, "days": 180}
}

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

    support_btn = InlineKeyboardButton(text="💬 Qõllab-quvvatlash", url=f"https://t.me/{config.support_username}") if config.support_username else InlineKeyboardButton(text="💬 Qõllab-quvvatlash", callback_data="support_info")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Obunani rasmiylashtirish", callback_data="start_sub")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Kanal haqida", callback_data="about_channel"),
            support_btn
        ]
    ])
    
    welcome_text = (
        "🔥 <b>Shokhrux Lab — orzuingizdagi qomatga erishish vaqti keldi!</b>\n\n"
        "Bu shunchaki kanal emas, bu sizning <b>ozish va sog'lom hayot</b> sari transformatsiya markazingiz.\n"
        "Sizni nimalar kutmoqda:\n"
        "🏋️‍♂️ Samarali va sinalgan mashqlar dasturi\n"
        "🥗 To'g'ri ovqatlanish sirlari va parhezlar\n"
        "🔥 Tez va xavfsiz vazn tashlash texnikalari\n"
        "💪 Motivatsiya va kunlik qo'llab-quvvatlash!\n\n"
        "O'zgarishni bugundan boshlang! Mos tarifni tanlang va bizning jamoaga qo'shiling. 👇"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=keyboard
    )

@router.callback_query(F.data == "about_channel")
async def cb_about_channel(callback: CallbackQuery):
    await callback.message.answer("Bu yopiq kanalda siz ortiqcha vazndan qutilish, to'g'ri ovqatlanish va uy sharoitida (yoki zalda) shug'ullanish uchun eng zo'r dasturlarga ega bo'lasiz. Natijangiz kafolatlangan! 💪 Obunani rasmiylashtiring va safiga qo'shiling.")
    await callback.answer()

@router.callback_query(F.data == "start_sub")
async def cb_start_sub(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    stmt = select(User).where(User.telegram_id == callback.from_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    # Check if we need to collect additional info
    if not user or not user.full_name or not user.phone_number:
        await callback.message.answer("Obunani rasmiylashtirish uchun, iltimos, Ismingiz va Familiyangizni kiriting:")
        await state.set_state(RegistrationStates.waiting_for_name)
    else:
        await show_tariffs(callback.message)
    await callback.answer()

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
    
    await message.answer("✅ Ma'lumotlaringiz muvaffaqiyatli saqlandi!", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    
    await show_tariffs(message)

@router.message(RegistrationStates.waiting_for_phone)
async def process_phone_invalid(message: Message):
    await message.answer("Iltimos, raqamni yuborish uchun pastdagi tugmadan foydalaning.")

async def show_tariffs(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Oylik — 500,000 UZS", callback_data="tariff_1")],
        [InlineKeyboardButton(text="3 Oylik — 1,200,000 UZS", callback_data="tariff_3")],
        [InlineKeyboardButton(text="6 Oylik — 2,300,000 UZS", callback_data="tariff_6")]
    ])
    await message.answer("O'zingizga mos tarifni tanlang:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("tariff_"))
async def cb_tariff_selected(callback: CallbackQuery):
    tariff_months = callback.data.split("_")[1]
    tariff = TARIFFS[tariff_months]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ To'lov qildim", callback_data=f"pay_{tariff_months}")]
    ])
    
    text = (f"🧾 <b>Buyurtma tafsilotlari:</b>\n"
            f"Tarif: {tariff_months} oylik\n"
            f"Summa: {tariff['price']:,} UZS\n\n"
            f"⚠️ <b>Diqqat:</b> To'lov hozircha faqat karta orqali (qo'lda) qabul qilinadi.\n"
            f"Iltimos, ko'rsatilgan summani quyidagi kartaga o'tkazing: <code>8600 0000 0000 0000</code> (Qabul qiluvchi: Ism F.)\n\n"
            f"To'lovni amalga oshirgach, <b>«To'lov qildim»</b> tugmasini bosing.")
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
async def cb_mock_pay(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    tariff_months = callback.data.split("_")[1]
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
    
    # 2. Update or Create Subscription
    stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.status == "active"
    ).order_by(Subscription.expires_at.desc()).limit(1)
    
    result = await session.execute(stmt)
    current_sub = result.scalar_one_or_none()
    
    now = datetime.datetime.now(datetime.timezone.utc)
    
    if current_sub and current_sub.expires_at > now:
        # Extend existing active subscription
        started_at = current_sub.expires_at
        expires_at = started_at + datetime.timedelta(days=tariff['days'])
    else:
        # Create a brand new subscription
        started_at = now
        expires_at = now + datetime.timedelta(days=tariff['days'])
        
    subscription = Subscription(
        user_id=user_id,
        status="active",
        tariff_months=int(tariff_months),
        started_at=started_at,
        expires_at=expires_at
    )
    session.add(subscription)
    await session.commit()
    
    # 3. Notify Admins
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

    # 4. Generate Single-Use Invite Link
    try:
        channel_id = get_channel_id()
        invite_link = await bot.create_chat_invite_link(
            chat_id=channel_id,
            member_limit=1,
            name=f"Sub: {user_id} ({tariff_months}mo)"
        )
        link = invite_link.invite_link
    except Exception as e:
        print(f"Error creating invite link: {e}")
        if "chat not found" in str(e).lower():
            link = "⚠️ XATOLIK: Kanal topilmadi. .env faylida CHANNEL_ID noto'g'ri ko'rsatilgan!"
        else:
            link = f"⚠️ XATOLIK: {e}"
        
    date_str = expires_at.strftime("%Y-%m-%d %H:%M UTC")
    
    success_text = (
        f"⏳ <b>Sizning arizangiz adminga yuborildi!</b>\n\n"
        f"To'lov tasdiqlanishini kutmasdan, kanalga hoziroq qo'shilishingiz mumkin.\n"
        f"Sizning obunangiz vaqtincha {date_str} gacha faol.\n"
        f"⚠️ <i>Agar to'lov admin tomonidan tasdiqlanmasa, siz avtomatik ravishda kanaldan chiqarilasiz.</i>\n\n"
        f"🔗 <b>Sizning shaxsiy bir martalik kirish havolangiz:</b>\n{link}\n\n"
        f"Bu havolani hech kimga bermang. U faqat bir marta kirish uchun ishlaydi."
    )
    await callback.message.edit_text(success_text)
    await callback.answer()

@router.callback_query(F.data.startswith("admin_conf_"))
async def admin_confirm_payment(callback: CallbackQuery, session: AsyncSession):
    _, _, payment_id, user_id = callback.data.split("_")
    
    stmt = select(Payment).where(Payment.id == int(payment_id))
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()
    
    if payment and payment.status == "pending":
        payment.status = "completed"
        await session.commit()
        await callback.message.edit_text(callback.message.html_text + "\n\n✅ <b>To'lov tasdiqlandi.</b>")
    else:
        await callback.message.edit_text("To'lov topilmadi yoki allaqachon ko'rib chiqilgan.")
    await callback.answer()

@router.callback_query(F.data.startswith("admin_rej_"))
async def admin_reject_payment(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    _, _, payment_id, user_id = callback.data.split("_")
    user_id = int(user_id)
    
    stmt = select(Payment).where(Payment.id == int(payment_id))
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()
    
    if payment and payment.status == "pending":
        payment.status = "failed"
        
        # Mark recent subscription as expired
        sub_stmt = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status == "active"
        ).order_by(Subscription.expires_at.desc()).limit(1)
        sub_result = await session.execute(sub_stmt)
        sub = sub_result.scalar_one_or_none()
        
        if sub:
            sub.status = "expired"
            
        await session.commit()
        
        # Kick user
        try:
            channel_id = get_channel_id()
            await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
            await bot.unban_chat_member(chat_id=channel_id, user_id=user_id)
        except Exception as e:
            print(f"Failed to kick user {user_id}: {e}")
            
        await callback.message.edit_text(callback.message.html_text + "\n\n❌ <b>To'lov rad etildi. Foydalanuvchi kanaldan chiqarildi.</b>")
    else:
        await callback.message.edit_text("To'lov topilmadi yoki allaqachon ko'rib chiqilgan.")
    await callback.answer()

@router.callback_query(F.data == "support_info")
async def cb_support_info(callback: CallbackQuery):
    await callback.message.answer("Qo'llab-quvvatlash markazi bilan bog'lanish uchun adminimizga yozing.")
    await callback.answer()
