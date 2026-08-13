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

router = Router()

# In a real scenario, this should be in config.py, but using a default for demonstration
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1001234567890"))

TARIFFS = {
    "1": {"months": 1, "price": 150000, "days": 30},
    "3": {"months": 3, "price": 380000, "days": 90},
    "6": {"months": 6, "price": 700000, "days": 180}
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

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Начать / Оформить подписку", callback_data="start_sub"),
            InlineKeyboardButton(text="ℹ️ О канале", callback_data="about_channel")
        ]
    ])
    
    await message.answer(
        "Добро пожаловать в наше закрытое сообщество! Здесь вы найдете эксклюзивный контент.",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "about_channel")
async def cb_about_channel(callback: CallbackQuery):
    await callback.message.answer("Это приватное сообщество с уникальной аналитикой и материалами. Оформите подписку для доступа.")
    await callback.answer()

@router.callback_query(F.data == "start_sub")
async def cb_start_sub(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    stmt = select(User).where(User.telegram_id == callback.from_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    # Check if we need to collect additional info
    if not user or not user.full_name or not user.phone_number:
        await callback.message.answer("Для оформления подписки, пожалуйста, введите ваше Имя и Фамилию:")
        await state.set_state(RegistrationStates.waiting_for_name)
    else:
        await show_tariffs(callback.message)
    await callback.answer()

@router.message(RegistrationStates.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await message.answer("Поделитесь номером телефона для активации доступа:", reply_markup=kb)
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
    
    await message.answer("Ваши данные успешно сохранены!", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    
    await show_tariffs(message)

@router.message(RegistrationStates.waiting_for_phone)
async def process_phone_invalid(message: Message):
    await message.answer("Пожалуйста, используйте кнопку ниже, чтобы поделиться контактом.")

async def show_tariffs(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Месяц — 150,000 UZS", callback_data="tariff_1")],
        [InlineKeyboardButton(text="3 Месяца — 380,000 UZS", callback_data="tariff_3")],
        [InlineKeyboardButton(text="6 Месяцев — 700,000 UZS", callback_data="tariff_6")]
    ])
    await message.answer("Выберите подходящий тариф:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("tariff_"))
async def cb_tariff_selected(callback: CallbackQuery):
    tariff_months = callback.data.split("_")[1]
    tariff = TARIFFS[tariff_months]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", callback_data=f"pay_{tariff_months}")]
    ])
    
    text = (f"🧾 Детали заказа:\n"
            f"Тариф: {tariff_months} мес.\n"
            f"Сумма: {tariff['price']:,} UZS\n\n"
            f"Нажмите кнопку ниже, чтобы перейти к оплате.")
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
        status="completed"
    )
    session.add(payment)
    
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
    
    # 3. Generate Single-Use Invite Link
    try:
        invite_link = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            name=f"Sub: {user_id} ({tariff_months}mo)"
        )
        link = invite_link.invite_link
    except Exception as e:
        print(f"Error creating invite link: {e}")
        link = "ОШИБКА: У бота нет прав администратора в канале."
        
    date_str = expires_at.strftime("%Y-%m-%d %H:%M UTC")
    
    success_text = (
        f"✅ Оплата успешно получена!\n\n"
        f"Ваша подписка активна до {date_str}.\n\n"
        f"🔗 Ваш персональный одноразовый линк для входа:\n{link}\n\n"
        f"Никому не передавайте этот линк. Он действителен только для одного входа."
    )
    await callback.message.edit_text(success_text)
    await callback.answer()
