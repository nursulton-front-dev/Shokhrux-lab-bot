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
from bot import texts

router = Router()

def get_channel_id() -> int:
    return config.channel_id or int(os.getenv("CHANNEL_ID", "-1001234567890"))

TARIFFS = {
    "1": {"months": 1, "price": 500000, "days": 30},
    "3": {"months": 3, "price": 1200000, "days": 90},
    "6": {"months": 6, "price": 2300000, "days": 180}
}

def main_menu_keyboard(lang: str = "uz"):
    lang = lang or "uz"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.MENU_BUTTONS["profile"][lang]), KeyboardButton(text=texts.MENU_BUTTONS["subscribe"][lang])],
            [KeyboardButton(text=texts.MENU_BUTTONS["support"][lang]), KeyboardButton(text=texts.MENU_BUTTONS["lang"][lang])]
        ],
        resize_keyboard=True
    )

@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            language=None
        )
        session.add(user)
        await session.commit()

    if not user.language:
        # Prompt for language
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="set_lang_uz"), InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru")]
        ])
        await message.answer("🇺🇿 Iltimos, tilni tanlang:\n🇷🇺 Пожалуйста, выберите язык:", reply_markup=kb)
        return

    await message.answer(
        texts.WELCOME_TEXT[user.language],
        reply_markup=main_menu_keyboard(user.language)
    )
    await show_tariffs(message, user.language)

@router.callback_query(F.data.startswith("set_lang_"))
async def cb_set_lang(callback: CallbackQuery, session: AsyncSession):
    lang = callback.data.split("_")[2]
    user_id = callback.from_user.id
    
    stmt = select(User).where(User.telegram_id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user:
        user.language = lang
        await session.commit()
        
    await callback.message.delete()
    await callback.message.answer(
        texts.WELCOME_TEXT[lang],
        reply_markup=main_menu_keyboard(lang)
    )
    await show_tariffs(callback.message, lang)

@router.message(F.text.in_([texts.MENU_BUTTONS["support"]["uz"], texts.MENU_BUTTONS["support"]["ru"]]))
async def msg_support(message: Message, session: AsyncSession):
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
    if config.support_username:
        await message.answer(texts.SUPPORT_TEXT[lang].format(username=config.support_username))
    else:
        await message.answer(texts.SUPPORT_NO_UNAME[lang])

@router.message(F.text.in_([texts.MENU_BUTTONS["lang"]["uz"], texts.MENU_BUTTONS["lang"]["ru"]]))
async def msg_change_lang(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="set_lang_uz"), InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru")]
    ])
    await message.answer("🇺🇿 Iltimos, tilni tanlang:\n🇷🇺 Пожалуйста, выберите язык:", reply_markup=kb)

@router.message(Command("profile"))
@router.message(F.text.in_([texts.MENU_BUTTONS["profile"]["uz"], texts.MENU_BUTTONS["profile"]["ru"]]))
async def msg_profile(message: Message, session: AsyncSession):
    user_id = message.from_user.id
    
    stmt = select(User).where(User.telegram_id == user_id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
    sub_stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.status == "active"
    ).order_by(Subscription.expires_at.desc()).limit(1)
    
    current_sub = await session.scalar(sub_stmt)
    now = datetime.datetime.now(datetime.timezone.utc)
    
    if current_sub and current_sub.expires_at > now:
        status_emoji = "✅"
        status_text = texts.STATUS_ACTIVE[lang]
        expires_at_str = current_sub.expires_at.strftime("%Y-%m-%d %H:%M")
    else:
        status_emoji = "❌"
        status_text = texts.STATUS_EXPIRED[lang]
        expires_at_str = "-"
        
    text = texts.PROFILE_TEXT[lang].format(
        user_id=user_id,
        status_emoji=status_emoji,
        status_text=status_text,
        expires_at_str=expires_at_str
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.SUB_PROLONG[lang], callback_data="start_sub")]
    ])
    
    await message.answer(text, reply_markup=kb)

@router.message(F.text.in_([texts.MENU_BUTTONS["subscribe"]["uz"], texts.MENU_BUTTONS["subscribe"]["ru"]]))
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
    lang = user.language if user and user.language else "uz"
    
    if not user or not user.full_name or not user.phone_number:
        await message_obj.answer(texts.REG_ASK_NAME[lang])
        await state.set_state(RegistrationStates.waiting_for_name)
    else:
        await show_tariffs(message_obj, lang)

@router.message(RegistrationStates.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext, session: AsyncSession):
    await state.update_data(full_name=message.text)
    
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.REG_ASK_PHONE_KB[lang], request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await message.answer(texts.REG_ASK_PHONE[lang], reply_markup=kb)
    await state.set_state(RegistrationStates.waiting_for_phone)

@router.message(RegistrationStates.waiting_for_phone, F.contact)
async def process_phone(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    full_name = data.get("full_name")
    phone_number = message.contact.phone_number
    
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    lang = user.language if user and user.language else "uz"
    
    if user:
        user.full_name = full_name
        user.phone_number = phone_number
        await session.commit()
    
    await message.answer(texts.REG_SUCCESS[lang], reply_markup=main_menu_keyboard(lang))
    await state.clear()
    
    await show_tariffs(message, lang)

async def show_tariffs(message: Message, lang: str = "uz"):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Oylik / Мес. — 500,000 UZS", callback_data="tariff_1")],
        [InlineKeyboardButton(text="3 Oylik / Мес. — 1,200,000 UZS", callback_data="tariff_3")],
        [InlineKeyboardButton(text="6 Oylik / Мес. — 2,300,000 UZS", callback_data="tariff_6")]
    ])
    await message.answer(texts.CHOOSE_TARIFF[lang], reply_markup=keyboard)

@router.callback_query(F.data.startswith("tariff_"))
async def cb_tariff_selected(callback: CallbackQuery, session: AsyncSession):
    tariff_months = callback.data.split("_")[1]
    tariff = TARIFFS[tariff_months]
    user_id = callback.from_user.id
    
    stmt = select(User).where(User.telegram_id == user_id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
    # Calculate expiry date
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
        [InlineKeyboardButton(text=texts.PAY_BTN[lang], callback_data=f"pay_manual_{tariff_months}")],
        [InlineKeyboardButton(text=texts.BACK_BTN[lang], callback_data="start_sub")]
    ])
    
    text = texts.PAY_TARIFF_INFO[lang].format(
        months=tariff_months,
        price=f"{tariff['price']:,}",
        expires_at=expiry_date_str
    )
            
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("pay_manual_"))
async def cb_pay_manual(callback: CallbackQuery, session: AsyncSession):
    tariff_months = callback.data.split("_")[2]
    tariff = TARIFFS[tariff_months]
    user_id = callback.from_user.id
    
    stmt = select(User).where(User.telegram_id == user_id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.PAY_PAID_BTN[lang], callback_data=f"mock_pay_success_{tariff_months}")],
        [InlineKeyboardButton(text=texts.BACK_BTN[lang], callback_data=f"tariff_{tariff_months}")]
    ])
    
    text = texts.MANUAL_PAY_INFO[lang].format(price=f"{tariff['price']:,}")
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("mock_pay_success_"))
async def cb_mock_pay(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    tariff_months = callback.data.split("_")[3]
    tariff = TARIFFS[tariff_months]
    user_id = callback.from_user.id
    
    stmt = select(User).where(User.telegram_id == user_id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
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
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_conf_{payment.id}_{user_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_rej_{payment.id}_{user_id}")
            ]
        ])
        admin_text = (f"🆕 <b>Новая заявка на оплату!</b>\n\n"
                      f"Пользователь: <a href='tg://user?id={user_id}'>{callback.from_user.full_name or 'Пользователь'}</a>\n"
                      f"Тариф: {tariff_months} мес.\n"
                      f"Сумма: {tariff['price']:,} UZS\n\n"
                      f"Подтвердите получение средств.")
        
        for a_id in admin_ids:
            try:
                await bot.send_message(chat_id=a_id, text=admin_text, reply_markup=admin_kb)
            except Exception as e:
                print(f"Error notifying admin {a_id}: {e}")

    await callback.message.edit_text(texts.PENDING_ADMIN[lang])
    await session.commit()
    await callback.answer()
