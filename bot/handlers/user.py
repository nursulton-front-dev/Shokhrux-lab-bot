import asyncio
import datetime
import re
from html import escape
import logging
import os
from aiogram import Router, Bot, F
from aiogram.types import (
    Message,
    ChatJoinRequest,
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove,
    FSInputFile,
    InputMediaPhoto
)
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from bot.database.models import User, Subscription, Payment, Ticket, CashbackTransaction, UserFitnessProfile
from bot.services.subscription import is_user_subscription_active
from bot.states.registration import RegistrationStates, EditProfileStates
from bot.states.fitness import FitnessStates
from bot.states.support import SupportState
from bot.config import config
from bot.services.rahmat import create_payment_intent, process_successful_payment
from bot.services.click.protocol import build_pay_url as build_click_pay_url
from bot.services.payme.protocol import build_checkout_url as build_payme_checkout_url
from bot.services.payment_policy import PaymentValidationError
from bot import texts

logger = logging.getLogger(__name__)

router = Router()

def get_channel_id() -> int:
    return config.channel_id or int(os.getenv("CHANNEL_ID", "-1001234567890"))

TARIFFS = {
    "1": {"months": 1, "price": 500000, "days": 30},
    "3": {"months": 3, "price": 1200000, "days": 90},
    "6": {"months": 6, "price": 2300000, "days": 180}
}

async def get_main_menu_keyboard(session: AsyncSession, user_id: int, lang: str = "uz") -> ReplyKeyboardMarkup:
    is_active = await is_user_subscription_active(session, user_id)
    p_count = (await session.scalar(
        select(func.count()).select_from(Payment).where(Payment.user_id == user_id, Payment.status == "completed")
    )) or 0
    has_bought = (is_active or p_count > 0)
    return main_menu_keyboard(lang, is_active=is_active, has_bought=has_bought)

def main_menu_keyboard(lang: str = "uz", is_active: bool = False, has_bought: bool = False):
    """Builds the user's main reply keyboard per approved scheme.

    - Without an active subscription: [Profile] [Subscribe] / [Support]
    - With an active subscription: [Profile] [AI] / [Invite] [Prolong] / [Support]

    The language switch lives inside the profile card, not on the main menu.
    """
    lang = lang if lang in ("uz", "ru") else "uz"
    profile_btn = KeyboardButton(text=texts.MENU_BUTTONS["profile"][lang])
    support_btn = KeyboardButton(text=texts.MENU_BUTTONS["support"][lang])

    if is_active:
        ai_btn = KeyboardButton(text=texts.MENU_BUTTONS["fitness_hub"][lang])
        ref_btn = KeyboardButton(text=texts.MENU_BUTTONS["referral"][lang])
        prolong_btn = KeyboardButton(text=texts.MENU_BUTTONS["prolong"][lang])
        keyboard = [
            [profile_btn, ai_btn],
            [ref_btn, prolong_btn],
            [support_btn],
        ]
    else:
        subscribe_btn = KeyboardButton(text=texts.MENU_BUTTONS["subscribe"][lang])
        keyboard = [
            [profile_btn, subscribe_btn],
            [support_btn],
        ]

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, session: AsyncSession, state: FSMContext):
    user_id = message.from_user.id
    stmt = select(User).where(User.telegram_id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    referrer_id = None
    if command and command.args and command.args.startswith("ref_"):
        try:
            ref_val = command.args.split("ref_")[1]
            if ref_val.isdigit():
                referrer_id = int(ref_val) if len(ref_val) <= 19 and int(ref_val) <= 2**63 - 1 else None
        except Exception:
            referrer_id = None

    if referrer_id and referrer_id == user_id:
        referrer_id = None

    if referrer_id:
        ref_check = await session.scalar(select(User).where(User.telegram_id == referrer_id))
        if not ref_check:
            referrer_id = None

    if not user:
        user = User(
            telegram_id=user_id,
            username=message.from_user.username,
            full_name=None,
            language=None,
            balance=0,
            referred_by=referrer_id
        )
        session.add(user)
        await session.commit()
    else:
        if not user.referred_by and referrer_id:
            p_count = await session.scalar(
                select(func.count()).select_from(Payment).where(Payment.user_id == user_id, Payment.status == "completed")
            ) or 0
            if p_count == 0:
                user.referred_by = referrer_id
                await session.commit()

    if not user.language:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="set_lang_uz"), InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru")]
        ])
        await message.answer("🇺🇿 Iltimos, tilni tanlang:\n🇷🇺 Пожалуйста, выберите язык:", reply_markup=kb)
        return

    if not user.full_name or not user.phone_number:
        await message.answer(texts.REG_ASK_NAME[user.language], reply_markup=ReplyKeyboardRemove())
        await state.set_state(RegistrationStates.waiting_for_name)
        return

    main_kb = await get_main_menu_keyboard(session, user_id, user.language)
    await message.answer(
        texts.WELCOME_TEXT[user.language],
        reply_markup=main_kb
    )
    await show_tariffs(message, user.language)

@router.callback_query(F.data.startswith("set_lang_"))
async def cb_set_lang(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    lang = callback.data.split("_")[2]
    user_id = callback.from_user.id
    
    stmt = select(User).where(User.telegram_id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user:
        user.language = lang
        await session.commit()
        
    await callback.message.delete()
    
    if not user.full_name or not user.phone_number:
        await callback.message.answer(texts.REG_ASK_NAME[lang], reply_markup=ReplyKeyboardRemove())
        await state.set_state(RegistrationStates.waiting_for_name)
        return

    main_kb = await get_main_menu_keyboard(session, user_id, lang)
    await callback.message.answer(
        texts.WELCOME_TEXT[lang],
        reply_markup=main_kb
    )

@router.message(F.text.in_([texts.MENU_BUTTONS["support"]["uz"], texts.MENU_BUTTONS["support"]["ru"]]))
async def msg_support(message: Message, session: AsyncSession, state: FSMContext):
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
    stmt_ticket = select(Ticket).where(
        Ticket.user_id == message.from_user.id,
        Ticket.status.in_(["open", "in_progress"])
    )
    ticket = await session.scalar(stmt_ticket)
    
    if ticket:
        if ticket.status == "in_progress":
            await message.answer(texts.SUPPORT_IN_SESSION_HINT[lang], reply_markup=ReplyKeyboardRemove())
            await state.set_state(SupportState.in_ticket_session)
        else:
            await message.answer(texts.SUPPORT_ALREADY_OPEN[lang])
        return

    await message.answer(texts.SUPPORT_PROMPT[lang], reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=texts.BACK_BTN[lang], callback_data="cancel_ticket")]]))
    await state.set_state(SupportState.waiting_for_ticket_text)

@router.callback_query(F.data == "cancel_ticket")
async def cb_cancel_ticket(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    stmt = select(User).where(User.telegram_id == callback.from_user.id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    await state.clear()
    await callback.message.delete()
    main_kb = await get_main_menu_keyboard(session, callback.from_user.id, lang)
    await callback.message.answer(texts.WELCOME_TEXT[lang], reply_markup=main_kb)
    await callback.answer()

@router.message(SupportState.waiting_for_ticket_text, F.text)
async def process_ticket_text(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
    ticket = Ticket(
        user_id=message.from_user.id,
        status="open",
        text=message.text
    )
    session.add(ticket)
    await session.commit()
    
    main_kb = await get_main_menu_keyboard(session, message.from_user.id, lang)
    await message.answer(texts.SUPPORT_TICKET_CREATED[lang], reply_markup=main_kb)
    await state.set_state(SupportState.in_ticket_session)
    
    admin_ids = config.get_admin_ids
    for a_id in admin_ids:
        try:
            await bot.send_message(a_id, f"🆕 <b>Новая заявка в поддержку!</b>\nОт: {escape(message.from_user.full_name)} (ID: <code>{message.from_user.id}</code>)\n\n<i>{escape(message.text[:200])}...</i>")
        except:
            pass

@router.message(SupportState.in_ticket_session, F.any)
async def process_user_ticket_message(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    stmt_ticket = select(Ticket).where(
        Ticket.user_id == message.from_user.id,
        Ticket.status.in_(["open", "in_progress"])
    )
    ticket = await session.scalar(stmt_ticket)
    
    stmt_user = select(User).where(User.telegram_id == message.from_user.id)
    user = await session.scalar(stmt_user)
    lang = user.language if user and user.language else "uz"
    
    if not ticket:
        await state.clear()
        return
        
    if ticket.status == "open":
        wait_text = "⏳ Iltimos, administrator javobini kuting." if lang == "uz" else "⏳ Пожалуйста, подождите ответа администратора."
        await message.answer(wait_text)
        return
        
    if ticket.admin_id:
        await bot.copy_message(
            chat_id=ticket.admin_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )

@router.message(F.text.in_([texts.MENU_BUTTONS["lang"]["uz"], texts.MENU_BUTTONS["lang"]["ru"]]))
async def msg_change_lang(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="set_lang_uz"), InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru")]
    ])
    await message.answer("🇺🇿 Iltimos, tilni tanlang:\n🇷🇺 Пожалуйста, выберите язык:", reply_markup=kb)

@router.message(Command("referral"))
@router.message(F.text.in_([
    texts.MENU_BUTTONS["referral"]["uz"], 
    texts.MENU_BUTTONS["referral"]["ru"], 
    "🤝 Do'stni taklif qilish", 
    "🤝 Пригласить друга", 
    "🎁 Do'stni taklif qilish (+30 000 UZS)", 
    "🎁 Пригласить друга (+30 000 UZS)",
    "🎁 Do'stni taklif qilish",
    "🎁 Пригласить друга"
]))
@router.callback_query(F.data == "invite_friend")
async def msg_referral_info(event: Message | CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = event.from_user.id
    user = await session.scalar(select(User).where(User.telegram_id == user_id))
    lang = user.language if user and user.language else "uz"
    
    invited_count = (await session.scalar(
        select(func.count()).select_from(User).where(User.referred_by == user_id)
    )) or 0

    bot_info = await bot.get_me()
    bot_username = bot_info.username or "Bot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    share_url = f"https://t.me/share/url?url={ref_link}&text=" + (
        "🔥 Prisoedinyaysya k zakrytomu fitnes-klubu!" if lang == "ru" else "🔥 Yopiq fitnes-klubga qo'shiling va formaga kiring!"
    )
    
    card_text = texts.REF_PROGRAM_TEXT[lang].format(
        ref_link=ref_link,
        balance=user.balance or 0,
        invited_count=invited_count
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.SHARE_REF_BTN[lang], url=share_url)]
    ])
    if isinstance(event, CallbackQuery):
        await event.message.answer(card_text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(card_text, reply_markup=kb, parse_mode="HTML")

@router.message(Command("profile"))
@router.message(F.text.in_([texts.MENU_BUTTONS["profile"]["uz"], texts.MENU_BUTTONS["profile"]["ru"]]))
async def msg_profile(message: Message, session: AsyncSession, bot: Bot):
    await send_profile_info(message.from_user.id, message, session, bot)

DEFAULT_AVATAR_URL = "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=500&auto=format&fit=crop&q=80"

async def send_profile_info(user_id: int, message_obj: Message | CallbackQuery, session: AsyncSession, bot: Bot, edit: bool = False):
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
        
    invited_count = await session.scalar(
        select(func.count()).select_from(User).where(User.referred_by == user_id)
    ) or 0
    
    prof_stmt = select(UserFitnessProfile).where(UserFitnessProfile.user_id == user_id)
    prof = await session.scalar(prof_stmt)
    
    if prof:
        gender_str = texts.GENDER_OPTIONS.get(prof.gender, {}).get(lang, prof.gender or "👨 Erkak")
        height_cm_str = f"{prof.height_cm:.0f} sm" if lang == "uz" else f"{prof.height_cm:.0f} см"
        init_w = prof.initial_weight_kg if prof.initial_weight_kg is not None else prof.weight_kg
        initial_weight_str = f"{init_w:.1f} kg" if lang == "uz" else f"{init_w:.1f} кг"
        current_weight_str = f"{prof.weight_kg:.1f} kg" if lang == "uz" else f"{prof.weight_kg:.1f} кг"
        goal_str = texts.GOAL_OPTIONS.get(prof.goal, {}).get(lang, prof.goal)
    else:
        gender_str = texts.NOT_SPECIFIED[lang]
        height_cm_str = texts.NOT_SPECIFIED[lang]
        initial_weight_str = texts.NOT_SPECIFIED[lang]
        current_weight_str = texts.NOT_SPECIFIED[lang]
        goal_str = texts.NOT_SPECIFIED[lang]

    bot_info = await bot.get_me()
    bot_username = bot_info.username or "Bot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    balance_formatted = f"{user.balance or 0:,}"
    
    caption_text = texts.PROFILE_TEXT[lang].format(
        user_id=user_id,
        full_name=escape(user.full_name or "-"),
        phone_number=escape(user.phone_number or "-"),
        status_emoji=status_emoji,
        status_text=status_text,
        expires_at_str=expires_at_str,
        gender=gender_str,
        height_cm=height_cm_str,
        initial_weight_kg=initial_weight_str,
        current_weight_kg=current_weight_str,
        goal=goal_str,
        balance=balance_formatted,
        invited_count=invited_count,
        ref_link=ref_link
    )
    
    inline_keyboard = [
        [
            InlineKeyboardButton(text=texts.EDIT_PHOTO_BTN[lang], callback_data="profile_edit_photo"),
            InlineKeyboardButton(text=texts.EDIT_PARAMS_BTN[lang], callback_data="profile_edit_params")
        ],
        [
            InlineKeyboardButton(text=texts.CHANGE_LANG_BTN[lang], callback_data="profile_change_lang")
        ]
    ]
    
    if current_sub and current_sub.expires_at > now and current_sub.tariff_months == 6:
        inline_keyboard.append([
            InlineKeyboardButton(text=texts.VIP_GROUP_BTN[lang], callback_data="vip_group_link")
        ])
        
    sub_label = texts.SUB_PROLONG[lang] if (current_sub and current_sub.expires_at > now) else texts.MENU_BUTTONS["subscribe"][lang]
    inline_keyboard.append([
        InlineKeyboardButton(text=sub_label, callback_data="start_sub")
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    photo_to_send = user.photo_file_id if user and user.photo_file_id else DEFAULT_AVATAR_URL

    if isinstance(message_obj, CallbackQuery):
        try:
            await message_obj.message.edit_media(
                media=InputMediaPhoto(media=photo_to_send, caption=caption_text, parse_mode="HTML"),
                reply_markup=kb
            )
            await message_obj.answer()
        except Exception:
            try:
                await message_obj.message.delete()
            except Exception:
                pass
            await message_obj.message.answer_photo(photo=photo_to_send, caption=caption_text, reply_markup=kb, parse_mode="HTML")
            await message_obj.answer()
    else:
        await message_obj.answer_photo(photo=photo_to_send, caption=caption_text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "profile_edit_photo")
async def cb_profile_edit_photo(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await session.scalar(select(User).where(User.telegram_id == callback.from_user.id))
    lang = user.language if user and user.language else "uz"
    await state.set_state(FitnessStates.waiting_for_photo)
    await callback.message.answer(texts.PROMPT_PHOTO_UPLOAD[lang], reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
    await callback.answer()

@router.message(FitnessStates.waiting_for_photo, F.photo)
async def process_profile_photo(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    photo = message.photo[-1]
    user = await session.scalar(select(User).where(User.telegram_id == message.from_user.id))
    lang = user.language if user and user.language else "uz"
    
    user.photo_file_id = photo.file_id
    await session.commit()
    await state.clear()
    
    await message.answer(texts.PHOTO_UPDATED_SUCCESS[lang])
    main_kb = await get_main_menu_keyboard(session, message.from_user.id, lang)
    await message.answer(texts.WELCOME_TEXT[lang], reply_markup=main_kb)
    await send_profile_info(message.from_user.id, message, session, bot, edit=False)

@router.callback_query(F.data == "profile_edit_params")
async def cb_profile_edit_params(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await session.scalar(select(User).where(User.telegram_id == callback.from_user.id))
    lang = user.language if user and user.language else "uz"
    await state.set_state(FitnessStates.waiting_for_profile_goal)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.GOAL_OPTIONS["weight_loss"][lang], callback_data="goal_weight_loss")],
        [InlineKeyboardButton(text=texts.GOAL_OPTIONS["keep_fit"][lang], callback_data="goal_keep_fit")],
        [InlineKeyboardButton(text=texts.GOAL_OPTIONS["muscle_gain"][lang], callback_data="goal_muscle_gain")]
    ])
    await callback.message.answer(texts.PROFILE_ASK_GOAL[lang], reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "profile_change_lang")
async def cb_profile_change_lang(callback: CallbackQuery, session: AsyncSession):
    user = await session.scalar(select(User).where(User.telegram_id == callback.from_user.id))
    lang = user.language if user and user.language else "uz"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")
        ],
        [
            InlineKeyboardButton(text="◀️ Orqaga / Назад", callback_data="profile_back")
        ]
    ])
    text = "🌐 <b>Tilni tanlang / Выберите язык:</b>"
    try:
        await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.in_(["lang_uz", "lang_ru"]))
async def cb_profile_set_lang(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    new_lang = "uz" if callback.data == "lang_uz" else "ru"
    user = await session.scalar(select(User).where(User.telegram_id == callback.from_user.id))
    if user:
        user.language = new_lang
        await session.commit()
    
    main_kb = await get_main_menu_keyboard(session, callback.from_user.id, new_lang)
    confirm_msg = "✅ Til o'zgartirildi!" if new_lang == "uz" else "✅ Язык успешно изменён!"
    await callback.message.answer(confirm_msg, reply_markup=main_kb)
    await send_profile_info(callback.from_user.id, callback, session, bot, edit=True)

@router.callback_query(F.data == "profile_back")
async def cb_profile_back(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    await send_profile_info(callback.from_user.id, callback, session, bot, edit=True)

@router.callback_query(F.data == "vip_group_link")
async def cb_vip_group_link(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    """Gives an active 6-month client their personal VIP-group invite link.
    Reuses the stored link when present, otherwise issues a fresh one."""
    user_id = callback.from_user.id
    user = await session.scalar(select(User).where(User.telegram_id == user_id).with_for_update())
    lang = user.language if user and user.language else "uz"

    now = datetime.datetime.now(datetime.timezone.utc)
    current_sub = await session.scalar(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
            Subscription.tariff_months == 6,
        ).order_by(Subscription.expires_at.desc()).limit(1)
    )

    if not current_sub or current_sub.expires_at <= now:
        await callback.answer(texts.GUARD_ACCESS_DENIED[lang], show_alert=True)
        return

    vip_link = current_sub.vip_invite_link
    vip_chat_id = config.vip_chat_id
    if not vip_link and vip_chat_id:
        try:
            vip_link_obj = await bot.create_chat_invite_link(
                chat_id=vip_chat_id, creates_join_request=True, expire_date=current_sub.expires_at,
                name=f"VIP: {user_id}", request_timeout=10
            )
            vip_link = vip_link_obj.invite_link
            current_sub.vip_invite_link = vip_link
            await session.commit()
        except Exception as e:
            logger.error(f"Failed to create VIP invite link for user {user_id}: {e}")

    await session.commit()
    if vip_link:
        await callback.message.answer(texts.VIP_GROUP_CARD[lang].format(vip_link=vip_link))
    else:
        await callback.message.answer(texts.VIP_GROUP_LINK_ERROR[lang])
    await callback.answer()

@router.callback_query(F.data == "profile_edit_name")
async def cb_profile_edit_name(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await session.scalar(select(User).where(User.telegram_id == callback.from_user.id))
    lang = user.language if user and user.language else "uz"
    await state.set_state(EditProfileStates.waiting_for_name)
    await callback.message.answer(texts.PROMPT_NEW_NAME[lang])
    await callback.answer()

@router.message(EditProfileStates.waiting_for_name, F.text)
async def process_edit_name(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user = await session.scalar(select(User).where(User.telegram_id == message.from_user.id))
    lang = user.language if user and user.language else "uz"
    
    name = (message.text or "").strip()
    if not 1 <= len(name) <= 100:
        await message.answer("Введите имя длиной от 1 до 100 символов.")
        return
    user.full_name = name
    await session.commit()
    await state.clear()
    
    await message.answer(texts.NAME_UPDATED[lang])
    await send_profile_info(message.from_user.id, message, session, bot)

@router.callback_query(F.data == "profile_edit_phone")
async def cb_profile_edit_phone(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await session.scalar(select(User).where(User.telegram_id == callback.from_user.id))
    lang = user.language if user and user.language else "uz"
    await state.set_state(EditProfileStates.waiting_for_phone)
    
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.REG_ASK_PHONE_KB[lang], request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await callback.message.answer(texts.PROMPT_NEW_PHONE[lang], reply_markup=kb)
    await callback.answer()

@router.message(EditProfileStates.waiting_for_phone, F.contact | F.text)
async def process_edit_phone(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user = await session.scalar(select(User).where(User.telegram_id == message.from_user.id))
    lang = user.language if user and user.language else "uz"
    
    phone = _validated_phone(message)
    if phone is None:
        await message.answer("Отправьте свой контакт или номер в формате +998901234567.")
        return
    user.phone_number = phone
        
    await session.commit()
    await state.clear()
    
    main_kb = await get_main_menu_keyboard(session, message.from_user.id, lang)
    await message.answer(texts.PHONE_UPDATED[lang], reply_markup=main_kb)
    await send_profile_info(message.from_user.id, message, session, bot)

@router.callback_query(F.data == "invite_friend")
async def cb_invite_friend(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user = await session.scalar(select(User).where(User.telegram_id == user_id))
    lang = user.language if user and user.language else "uz"
    
    bot_info = await bot.get_me()
    bot_username = bot_info.username or "Bot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    share_url = f"https://t.me/share/url?url={ref_link}&text=" + (
        "🔥 Prisoedinyaysya k zakrytomu fitnes-klubu!" if lang == "ru" else "🔥 Yopiq fitnes-klubga qo'shiling!"
    )
    
    card_text = texts.REFERRAL_CARD_TEXT[lang].format(ref_link=ref_link)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.SHARE_REF_BTN[lang], url=share_url)],
        [InlineKeyboardButton(text=texts.BACK_BTN[lang], callback_data="back_to_profile")]
    ])
    await callback.message.edit_text(card_text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "back_to_profile")
async def cb_back_to_profile(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    await send_profile_info(callback.from_user.id, callback.message, session, bot, edit=True)
    await callback.answer()



@router.message(F.text.in_([
    texts.MENU_BUTTONS["subscribe"]["uz"], texts.MENU_BUTTONS["subscribe"]["ru"],
    texts.SUB_PROLONG["uz"], texts.SUB_PROLONG["ru"],
    "🚀 Obuna bo'lish", "🚀 Оформить подписку",
    "🚀 Obunani uzaytirish", "🚀 Продлить подписку"
]))
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
        await message_obj.answer(texts.REG_ASK_NAME[lang], reply_markup=ReplyKeyboardRemove())
        await state.set_state(RegistrationStates.waiting_for_name)
    else:
        await show_tariffs(message_obj, lang)

@router.message(RegistrationStates.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext, session: AsyncSession):
    name = (message.text or "").strip()
    if not 1 <= len(name) <= 100:
        await message.answer("Введите имя длиной от 1 до 100 символов.")
        return
    await state.update_data(full_name=name)
    
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

def _validated_phone(message: Message) -> str | None:
    if message.contact:
        if message.contact.user_id != message.from_user.id:
            return None
        value = message.contact.phone_number
    else:
        value = message.text or ""
    value = re.sub(r"[ ()-]", "", value.strip())
    return value if re.fullmatch(r"\+?[1-9][0-9]{6,14}", value) else None


@router.message(RegistrationStates.waiting_for_phone, F.contact | F.text)
async def process_phone(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    full_name = data.get("full_name")
    
    phone_number = _validated_phone(message)
    if phone_number is None:
        await message.answer("Отправьте свой контакт или номер в формате +998901234567.")
        return
        
    stmt = select(User).where(User.telegram_id == message.from_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    lang = user.language if user and user.language else "uz"
    
    if user:
        user.full_name = full_name
        user.phone_number = phone_number
        await session.commit()
    
    await message.answer(texts.REG_SUCCESS[lang], reply_markup=ReplyKeyboardRemove())
    await state.clear()
    
    main_kb = await get_main_menu_keyboard(session, message.from_user.id, lang)
    await message.answer(texts.WELCOME_TEXT[lang], reply_markup=main_kb)
    await show_tariffs(message, lang)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _tariffs_banner_path(lang: str) -> str:
    """Absolute path to the tariff banner for the user's interface language."""
    configured = config.tariffs_img(lang if lang in ("uz", "ru") else "uz")
    return configured if os.path.isabs(configured) else os.path.join(PROJECT_ROOT, configured)


async def show_tariffs(message_obj: Message, lang: str = "uz"):
    lang = lang if lang in ("uz", "ru") else "uz"
    caption_text = texts.ALL_TARIFFS_CARD[lang]
    if len(caption_text) > 1024:
        caption_text = caption_text[:1021] + "..."
    
    t_1 = TARIFFS["1"]
    t_3 = TARIFFS["3"]
    t_6 = TARIFFS["6"]
    
    btn_1_text = f"🥉 1 {'oylik' if lang == 'uz' else 'месяц'} — {t_1['price']:,} UZS".replace(",", " ")
    btn_3_text = f"🥈 3 {'oylik' if lang == 'uz' else 'месяца'} — {t_3['price']:,} UZS".replace(",", " ")
    btn_6_text = f"🥇 6 {'oylik' if lang == 'uz' else 'месяцев'} — {t_6['price']:,} UZS".replace(",", " ")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_1_text, callback_data="tariff_1")],
        [InlineKeyboardButton(text=btn_3_text, callback_data="tariff_3")],
        [InlineKeyboardButton(text=btn_6_text, callback_data="tariff_6")]
    ])
    
    banner_path = _tariffs_banner_path(lang)
    if await asyncio.to_thread(os.path.exists, banner_path):
        photo_file = FSInputFile(banner_path)
        await message_obj.answer_photo(photo=photo_file, caption=caption_text, reply_markup=kb, parse_mode="HTML")
    else:
        logger.warning("Tariff banner missing for lang=%s: %s", lang, banner_path)
        await message_obj.answer(caption_text, reply_markup=kb, parse_mode="HTML")



@router.callback_query(F.data.regexp(r"^tariff_(1|3|6)$"))
async def cb_tariff_selected(callback: CallbackQuery, session: AsyncSession):
    tariff_months = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    stmt = select(User).where(User.telegram_id == user_id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
    tariff = TARIFFS[tariff_months]
    tariff_price = tariff['price']
    
    if user and user.balance and user.balance > 0:
        cashback_used = min(user.balance, tariff_price)
        final_price = tariff_price - cashback_used
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=texts.CASHBACK_USE_BTN[lang], callback_data=f"select_pay_{tariff_months}_1")],
            [InlineKeyboardButton(text=texts.CASHBACK_FULL_BTN[lang], callback_data=f"select_pay_{tariff_months}_0")],
            [InlineKeyboardButton(text=texts.BACK_BTN[lang], callback_data="start_sub")]
        ])
        text = texts.CASHBACK_ASK[lang].format(
            balance=f"{user.balance:,}",
            tariff_price=f"{tariff_price:,}",
            final_price=f"{final_price:,}"
        )
        await callback.message.answer(text, reply_markup=kb)
        await callback.answer()
    else:
        await render_payment_info(callback, tariff_months, use_cb=0, session=session)

@router.callback_query(F.data.regexp(r"^select_pay_(1|3|6)_[01]$"))
async def cb_select_pay(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split("_")
    tariff_months = parts[2]
    use_cb = int(parts[3])
    await render_payment_info(callback, tariff_months, use_cb, session)

async def render_payment_info(callback: CallbackQuery, tariff_months: str, use_cb: int, session: AsyncSession):
    tariff = TARIFFS[tariff_months]
    user_id = callback.from_user.id
    
    stmt = select(User).where(User.telegram_id == user_id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
    orig_price = tariff['price']
    cashback_used = min(orig_price, user.balance or 0) if use_cb == 1 else 0
    final_price = orig_price - cashback_used
    
    sub_stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.status == "active"
    ).order_by(Subscription.expires_at.desc()).limit(1)
    
    current_sub = await session.scalar(sub_stmt)
    now = datetime.datetime.now(datetime.timezone.utc)
    if current_sub and current_sub.expires_at > now:
        expires_at = current_sub.expires_at + datetime.timedelta(days=tariff['days'])
    else:
        expires_at = now + datetime.timedelta(days=tariff['days'])
        
    expiry_date_str = expires_at.strftime("%Y-%m-%d %H:%M UTC")
    
    if final_price == 0:
        btn_label = "⚡️ Keshbek bilan faollashtirish (0 UZS)" if lang == "uz" else "⚡️ Активировать за кешбэк (0 UZS)"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_label, callback_data=f"pay_cashback_full_{tariff_months}")],
            [InlineKeyboardButton(text=texts.BACK_BTN[lang], callback_data="start_sub")]
        ])
    else:
        manual_label = f"💳 Qo'lda to'lash (Karta)" if lang == "uz" else f"💳 Ручная оплата (Карта)"
        rows = []
        # Hosted checkouts first: they confirm themselves, manual payment does not.
        gateway_row = []
        if config.click_enabled:
            gateway_row.append(InlineKeyboardButton(
                text=texts.CLICK_PAY_BTN[lang], callback_data=f"pay_click_{tariff_months}_{use_cb}"))
        if config.payme_enabled:
            gateway_row.append(InlineKeyboardButton(
                text=texts.PAYME_PAY_BTN[lang], callback_data=f"pay_payme_{tariff_months}_{use_cb}"))
        if gateway_row:
            rows.append(gateway_row)
        rows.append([InlineKeyboardButton(text=manual_label, callback_data=f"pay_manual_{tariff_months}_{use_cb}")])
        rows.append([InlineKeyboardButton(text=texts.BACK_BTN[lang], callback_data="start_sub")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    
    price_text = f"<s>{orig_price:,}</s> ➔ <b>{final_price:,} UZS</b> (Keshbek: -{cashback_used:,} UZS)" if cashback_used > 0 else f"<b>{orig_price:,} UZS</b>"
    
    text = texts.PAY_TARIFF_INFO[lang].format(
        months=tariff_months,
        price=price_text,
        expires_at=expiry_date_str
    )
    
    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.regexp(r"^pay_rahmat_(1|3|6)(_[01])?$"))
async def cb_pay_rahmat(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    await callback.answer("Rahmat Pay временно недоступен. Используйте оплату картой.", show_alert=True)

def _payment_request_key(callback: CallbackQuery, method: str, months: int, use_cb: bool) -> str:
    if not isinstance(callback.message, Message):
        raise PaymentValidationError("Open the payment menu again")
    return f"{callback.from_user.id}:{callback.message.chat.id}:{callback.message.message_id}:{method}:{months}:{int(use_cb)}"


@router.callback_query(F.data.regexp(r"^pay_cashback_full_(1|3|6)$"))
async def cb_pay_cashback_full(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    months = int(callback.data.rsplit("_", 1)[1])
    try:
        payment = await create_payment_intent(
            session, user_id=callback.from_user.id, months=months, method="cashback", use_cashback=True,
            request_key=_payment_request_key(callback, "cashback", months, True))
        ok = await process_successful_payment(payment.id, session, bot)
    except PaymentValidationError:
        await callback.answer("Недостаточно кешбэка или платёж устарел. Откройте тариф заново.", show_alert=True)
        return
    await callback.answer("Подписка активирована. Ссылка будет отправлена автоматически." if ok
                          else "Этот платёж уже обработан.", show_alert=True)

async def _create_gateway_order(callback: CallbackQuery, session: AsyncSession, *,
                               method: str, months: int, use_cb: int) -> Payment | None:
    """Mint the pending order a hosted checkout will confirm, or explain why not."""
    try:
        payment = await create_payment_intent(
            session, user_id=callback.from_user.id, months=months, method=method,
            use_cashback=bool(use_cb),
            request_key=_payment_request_key(callback, method, months, bool(use_cb)))
    except PaymentValidationError:
        await callback.answer("Платёж устарел. Откройте тариф заново.", show_alert=True)
        return None
    if payment.status == "completed":
        await callback.answer("Этот заказ уже оплачен.", show_alert=True)
        return None
    if payment.status != "pending":
        # A cancelled attempt closes its order for good; a fresh tariff screen
        # mints a new one, so a stale checkout link stays unpayable.
        await callback.answer("Платёж отменён. Откройте тариф заново.", show_alert=True)
        return None
    if payment.amount <= 0:
        # A fully covered tariff is activated by cashback, never by a 0 UZS invoice.
        await callback.answer("Этот тариф покрыт кешбэком. Откройте тариф заново.", show_alert=True)
        return None
    return payment


async def _send_checkout_link(callback: CallbackQuery, *, lang: str, payment: Payment, url: str,
                              info: dict, open_btn: dict, months: int, use_cb: int) -> None:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=open_btn[lang], url=url)],
        [InlineKeyboardButton(text=texts.BACK_BTN[lang], callback_data=f"select_pay_{months}_{use_cb}")]
    ])
    await callback.message.answer(
        info[lang].format(order_id=payment.id, price=f"{payment.amount:,}"),
        reply_markup=keyboard)
    await callback.answer()


async def _payer_language(session: AsyncSession, user_id: int) -> str:
    user = await session.scalar(select(User).where(User.telegram_id == user_id))
    return user.language if user and user.language else "uz"


@router.callback_query(F.data.regexp(r"^pay_click_(1|3|6)_[01]$"))
async def cb_pay_click(callback: CallbackQuery, session: AsyncSession):
    """Mint the order Click will confirm, then hand the payer its checkout link."""
    _, _, months_raw, use_cb_raw = callback.data.split("_")
    months, use_cb = int(months_raw), int(use_cb_raw)
    lang = await _payer_language(session, callback.from_user.id)
    if not config.click_enabled:
        await callback.answer("Click временно недоступен. Используйте оплату картой.", show_alert=True)
        return
    payment = await _create_gateway_order(callback, session, method="click", months=months, use_cb=use_cb)
    if payment is None:
        return
    url = build_click_pay_url(service_id=config.click_service_id, merchant_id=config.click_merchant_id,
                              amount=payment.amount, order_id=payment.id)
    await _send_checkout_link(callback, lang=lang, payment=payment, url=url,
                              info=texts.CLICK_PAY_INFO, open_btn=texts.CLICK_OPEN_BTN,
                              months=months, use_cb=use_cb)


@router.callback_query(F.data.regexp(r"^pay_payme_(1|3|6)_[01]$"))
async def cb_pay_payme(callback: CallbackQuery, session: AsyncSession):
    """Same flow as Click, against the Payme hosted checkout."""
    _, _, months_raw, use_cb_raw = callback.data.split("_")
    months, use_cb = int(months_raw), int(use_cb_raw)
    lang = await _payer_language(session, callback.from_user.id)
    if not config.payme_enabled:
        await callback.answer("Payme временно недоступен. Используйте оплату картой.", show_alert=True)
        return
    payment = await _create_gateway_order(callback, session, method="payme", months=months, use_cb=use_cb)
    if payment is None:
        return
    url = build_payme_checkout_url(merchant_id=config.payme_merchant_id,
                                   order_id=payment.id, amount_uzs=payment.amount)
    await _send_checkout_link(callback, lang=lang, payment=payment, url=url,
                              info=texts.PAYME_PAY_INFO, open_btn=texts.PAYME_OPEN_BTN,
                              months=months, use_cb=use_cb)

@router.callback_query(F.data.regexp(r"^pay_manual_(1|3|6)(_[01])?$"))
async def cb_pay_manual(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split("_")
    tariff_months = parts[2]
    use_cb = int(parts[3]) if len(parts) > 3 else 0
    
    tariff = TARIFFS[tariff_months]
    user_id = callback.from_user.id
    
    stmt = select(User).where(User.telegram_id == user_id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
    orig_price = tariff['price']
    cashback_used = min(orig_price, user.balance or 0) if use_cb == 1 else 0
    final_price = orig_price - cashback_used
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.PAY_PAID_BTN[lang], callback_data=f"mock_pay_success_{tariff_months}_{use_cb}")],
        [InlineKeyboardButton(text=texts.BACK_BTN[lang], callback_data=f"select_pay_{tariff_months}_{use_cb}")]
    ])
    
    text = texts.MANUAL_PAY_INFO[lang].format(price=f"{final_price:,}")
    if cashback_used > 0:
        text += f"\n\n🎁 (Keshbek ishlatildi: {cashback_used:,} UZS)"
        
    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.regexp(r"^mock_pay_success_(1|3|6)(_[01])?$"))
async def cb_mock_pay(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    parts = callback.data.split("_")
    tariff_months = parts[3]
    use_cb = int(parts[4]) if len(parts) > 4 else 0
    
    tariff = TARIFFS[tariff_months]
    user_id = callback.from_user.id
    
    stmt = select(User).where(User.telegram_id == user_id)
    user = await session.scalar(stmt)
    lang = user.language if user and user.language else "uz"
    
    orig_price = tariff['price']
    cashback_used = min(orig_price, user.balance or 0) if use_cb == 1 else 0
    final_price = orig_price - cashback_used
    
    try:
        payment = await create_payment_intent(
            session, user_id=user_id, months=int(tariff_months), method="manual_card", use_cashback=bool(use_cb),
            request_key=_payment_request_key(callback, "manual_card", int(tariff_months), bool(use_cb)))
    except PaymentValidationError:
        await callback.answer("Не удалось создать платёж. Откройте тариф заново.", show_alert=True)
        return
    if payment.status != "pending":
        await callback.answer("Этот платёж уже обработан.", show_alert=True)
        return
    final_price = payment.amount
    cashback_used = payment.cashback_applied

    admin_ids = config.get_admin_ids
    if admin_ids:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_conf_{payment.id}_{user_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_rej_{payment.id}_{user_id}")
            ]
        ])
        cb_info = f"\n🎁 Применен кешбэк: {cashback_used:,} UZS" if cashback_used > 0 else ""
        admin_text = (f"🆕 <b>Новая заявка на оплату!</b>\n\n"
                      f"Пользователь: <a href='tg://user?id={user_id}'>{escape(callback.from_user.full_name or 'Пользователь')}</a>\n"
                      f"Тариф: {tariff_months} мес.\n"
                      f"Сумма к оплате: <b>{final_price:,} UZS</b>{cb_info}\n\n"
                      f"Подтвердите получение средств.")
        
        for a_id in admin_ids:
            try:
                await bot.send_message(chat_id=a_id, text=admin_text, reply_markup=admin_kb)
            except Exception as e:
                logger.error(f"Error notifying admin {a_id}: {e}")

    await callback.message.edit_text(texts.PENDING_ADMIN[lang])
    await session.commit()
    await callback.answer()


@router.chat_join_request()
async def authorize_paid_join(request: ChatJoinRequest, session: AsyncSession, bot: Bot) -> None:
    if request.chat.id not in {config.channel_id, config.vip_chat_id}:
        return
    async with asyncio.timeout(20):
        await session.scalar(select(User).where(User.telegram_id == request.from_user.id).with_for_update())
        now = datetime.datetime.now(datetime.timezone.utc)
        link = request.invite_link.invite_link if request.invite_link else None
        column = Subscription.vip_invite_link if request.chat.id == config.vip_chat_id else Subscription.invite_link
        allowed = None
        if link:
            query = select(Subscription.id).where(
                Subscription.user_id == request.from_user.id, Subscription.status == "active",
                Subscription.expires_at > now, column == link)
            if request.chat.id == config.vip_chat_id:
                query = query.where(Subscription.tariff_months == 6)
            allowed = await session.scalar(query.limit(1))
        if allowed is not None:
            await bot.approve_chat_join_request(request.chat.id, request.from_user.id, request_timeout=10)
        else:
            await bot.decline_chat_join_request(request.chat.id, request.from_user.id, request_timeout=10)
        await session.commit()
