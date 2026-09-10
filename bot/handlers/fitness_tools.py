import asyncio
import html
import io
import logging
import math
import datetime
from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove,
    BufferedInputFile
)
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import re

from bot import texts
from bot.database.models import User, Subscription, CalorieLog, WeightLog, UserFitnessProfile
from bot.services.subscription import is_user_subscription_active
from bot.services.gemini_service import analyze_food_image, ask_nutritionist_ai, generate_weekly_meal_plan
from bot.services.charts import generate_weight_chart
from bot.states.fitness import FitnessStates
from bot.handlers.user import get_main_menu_keyboard
router = Router()
logger = logging.getLogger(__name__)
_chart_render_semaphore = asyncio.Semaphore(1)

def split_text_into_chunks(text: str, max_chunk_size: int = 3500) -> list[str]:
    """Bound even unbroken model output, counting supplementary Unicode safely."""
    if max_chunk_size < 2:
        raise ValueError("max_chunk_size must be at least 2")
    chunks: list[str] = []
    start = 0
    units = 0
    for index, char in enumerate(text):
        char_units = 2 if ord(char) > 0xFFFF else 1
        if units + char_units > max_chunk_size:
            chunks.append(text[start:index])
            start = index
            units = 0
        units += char_units
    if start < len(text):
        chunks.append(text[start:])
    return chunks or [text]

async def send_safe_message(msg_obj: Message, text: str, reply_markup=None) -> None:
    try:
        await msg_obj.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    except TelegramBadRequest as exc:
        if "parse entities" not in exc.message.lower():
            raise
        # None overrides the bot's default HTML parse mode for untrusted output.
        clean_text = html.unescape(re.sub(r'<[^>]+>', '', text))
        await msg_obj.answer(clean_text or text, reply_markup=reply_markup, parse_mode=None)

def get_back_keyboard(lang: str = "uz"):
    back_text = texts.BACK_BTN[lang if lang in texts.BACK_BTN else "uz"]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=back_text)]],
        resize_keyboard=True
    )

def get_ai_mode_keyboard(lang: str = "uz"):
    lang = lang if lang in ("uz", "ru") else "uz"
    btn_text = texts.AI_EXIT_BTN[lang]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=btn_text)]],
        resize_keyboard=True
    )

def get_smart_fitness_hub_reply_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    lang = lang if lang in ("uz", "ru") else "uz"
    back_text = texts.BACK_TO_MAIN_BTN[lang]
    keyboard = [
        [
            KeyboardButton(text=texts.MENU_BUTTONS["food_calories"][lang]),
            KeyboardButton(text=texts.MENU_BUTTONS["meal_plan"][lang])
        ],
        [
            KeyboardButton(text=texts.MENU_BUTTONS["weight_log"][lang]),
            KeyboardButton(text=texts.MENU_BUTTONS["allowed_foods"][lang])
        ],
        [
            KeyboardButton(text=texts.MENU_BUTTONS["ai_coach"][lang]),
            KeyboardButton(text=back_text)
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

async def check_guard_and_get_user(
    event: Message | CallbackQuery,
    session: AsyncSession,
) -> tuple[User | None, str, Subscription | None]:
    """Admit anyone holding an active subscription, whatever the tariff.

    Access used to depend on `tariff_months`, so a 1-month client was refused
    the AI tools. Every paid tariff now unlocks the same features; the tariffs
    differ only in duration, price and the VIP group.
    """
    user_id = event.from_user.id
    user = await session.scalar(select(User).where(User.telegram_id == user_id))
    lang = user.language if user and user.language else "uz"
    
    sub = await session.scalar(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status == "active"
        ).order_by(Subscription.expires_at.desc()).limit(1)
    )
    
    now = datetime.datetime.now(datetime.timezone.utc)
    if not sub or sub.expires_at <= now:
        text = texts.GUARD_ACCESS_DENIED[lang]
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=texts.MENU_BUTTONS["subscribe"][lang], callback_data="start_sub")
        ]])
        if isinstance(event, Message):
            await event.answer(text, reply_markup=kb)
        else:
            await event.message.answer(text, reply_markup=kb)
            await event.answer()
        return None, lang, None

    return user, lang, sub

async def ensure_fitness_profile(
    event: Message | CallbackQuery,
    session: AsyncSession, 
    state: FSMContext, 
    target_tool: str
) -> UserFitnessProfile | None:
    user_id = event.from_user.id
    message = event if isinstance(event, Message) else event.message
    profile = await session.scalar(select(UserFitnessProfile).where(UserFitnessProfile.user_id == user_id))
    if profile and profile.goal and profile.weight_kg:
        return profile

    user = await session.scalar(select(User).where(User.telegram_id == user_id))
    lang = user.language if user and user.language else "uz"

    await state.update_data(pending_tool=target_tool)
    await state.set_state(FitnessStates.waiting_for_profile_goal)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.GOAL_OPTIONS["weight_loss"][lang], callback_data="goal_weight_loss")],
        [InlineKeyboardButton(text=texts.GOAL_OPTIONS["keep_fit"][lang], callback_data="goal_keep_fit")],
        [InlineKeyboardButton(text=texts.GOAL_OPTIONS["muscle_gain"][lang], callback_data="goal_muscle_gain")]
    ])
    await message.answer(texts.PROFILE_ASK_GOAL[lang], reply_markup=kb, parse_mode="HTML")
    return None

async def show_smart_fitness_hub(event: Message | CallbackQuery, session: AsyncSession, state: FSMContext):
    user, lang, sub = await check_guard_and_get_user(event, session)
    if not user:
        return

    profile = await session.scalar(select(UserFitnessProfile).where(UserFitnessProfile.user_id == user.telegram_id))
    if not profile or not profile.goal or not profile.weight_kg:
        msg_obj = event if isinstance(event, Message) else event.message
        await ensure_fitness_profile(event, session, state, "hub")
        if isinstance(event, CallbackQuery):
            await event.answer()
        return

    text = texts.FITNESS_HUB_TITLE[lang]
    reply_kb = get_smart_fitness_hub_reply_keyboard(lang)

    if isinstance(event, CallbackQuery):
        await event.message.answer(text, reply_markup=reply_kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=reply_kb, parse_mode="HTML")

# ======================== ⚡️ SMART FITNESS HUB ========================

@router.message(F.text.in_([texts.MENU_BUTTONS["fitness_hub"]["uz"], texts.MENU_BUTTONS["fitness_hub"]["ru"], "⚡️ Smart Fitness Hub"]))
async def msg_smart_fitness_hub(message: Message, session: AsyncSession, state: FSMContext):
    await show_smart_fitness_hub(message, session, state)

@router.callback_query(F.data == "open_fitness_hub")
async def cb_open_fitness_hub(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await show_smart_fitness_hub(callback, session, state)

@router.message(F.text.in_([
    texts.BACK_TO_MAIN_BTN["uz"], texts.BACK_TO_MAIN_BTN["ru"],
    "◀️ Asosiy menyuga qaytish", "◀️ Вернуться в главное меню", "◀️ Назад"
]))
@router.callback_query(F.data == "hub_back_main")
async def msg_hub_back_main(event: Message | CallbackQuery, session: AsyncSession, state: FSMContext):
    if state:
        await state.clear()
    user_id = event.from_user.id
    user = await session.scalar(select(User).where(User.telegram_id == user_id))
    lang = user.language if user and user.language else "uz"
    main_kb = await get_main_menu_keyboard(session, user_id, lang)
    
    if isinstance(event, CallbackQuery):
        try:
            await event.message.delete()
        except Exception:
            pass
        await event.message.answer(texts.WELCOME_TEXT[lang], reply_markup=main_kb)
        await event.answer()
    else:
        await event.answer(texts.WELCOME_TEXT[lang], reply_markup=main_kb)

# ======================== 📋 АНКЕТА ПОЛЬЗОВАТЕЛЯ ========================

@router.callback_query(FitnessStates.waiting_for_profile_goal, F.data.startswith("goal_"))
async def process_profile_goal(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    goal_code = callback.data.replace("goal_", "")
    user_id = callback.from_user.id
    user = await session.scalar(select(User).where(User.telegram_id == user_id))
    lang = user.language if user and user.language else "uz"
    if goal_code not in texts.GOAL_OPTIONS:
        await callback.answer("Некорректная цель" if lang == "ru" else "Noto'g'ri maqsad", show_alert=True)
        return
    
    await state.update_data(profile_goal=goal_code)
    await state.set_state(FitnessStates.waiting_for_profile_weight)
    
    await callback.message.answer(texts.PROFILE_ASK_WEIGHT[lang], parse_mode="HTML")
    await callback.answer()

@router.message(FitnessStates.waiting_for_profile_weight)
async def process_profile_weight(message: Message, state: FSMContext, session: AsyncSession):
    user = await session.scalar(select(User).where(User.telegram_id == message.from_user.id))
    lang = user.language if user and user.language else "uz"
    
    raw = (message.text or "").strip().replace(",", ".")
    try:
        weight_val = float(raw)
        if not math.isfinite(weight_val) or weight_val < 30 or weight_val > 300:
            raise ValueError
    except ValueError:
        err = "❌ Noto'g'ri vazn kg da. (30-300 aralig'ida kiriting):" if lang == "uz" else "❌ Некорректный вес в кг (от 30 до 300):"
        await message.answer(err)
        return
        
    await state.update_data(profile_weight=weight_val)
    await state.set_state(FitnessStates.waiting_for_profile_height)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.SKIP_BTN[lang], callback_data="height_skip")]
    ])
    await message.answer(texts.PROFILE_ASK_HEIGHT[lang], reply_markup=kb, parse_mode="HTML")

@router.callback_query(FitnessStates.waiting_for_profile_height, F.data == "height_skip")
async def process_profile_height_skip(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await session.scalar(select(User).where(User.telegram_id == callback.from_user.id))
    lang = user.language if user and user.language else "uz"
    await state.update_data(profile_height=170.0)
    await state.set_state(FitnessStates.waiting_for_profile_photo)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.SKIP_BTN[lang], callback_data="photo_skip")]
    ])
    await callback.message.answer(texts.PROFILE_ASK_BODY_PHOTO[lang], reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.message(FitnessStates.waiting_for_profile_height)
async def process_profile_height_text(message: Message, state: FSMContext, session: AsyncSession):
    user = await session.scalar(select(User).where(User.telegram_id == message.from_user.id))
    lang = user.language if user and user.language else "uz"
    
    raw = (message.text or "").strip().replace(",", ".")
    try:
        height_val = float(raw)
        if not math.isfinite(height_val) or height_val < 100 or height_val > 250:
            raise ValueError
    except ValueError:
        err = "❌ Noto'g'ri bo'y sm da. (100-250 aralig'ida kiriting):" if lang == "uz" else "❌ Некорректный рост в см (от 100 до 250):"
        await message.answer(err)
        return
        
    await state.update_data(profile_height=height_val)
    await state.set_state(FitnessStates.waiting_for_profile_photo)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.SKIP_BTN[lang], callback_data="photo_skip")]
    ])
    await message.answer(texts.PROFILE_ASK_BODY_PHOTO[lang], reply_markup=kb, parse_mode="HTML")

@router.callback_query(FitnessStates.waiting_for_profile_photo, F.data == "photo_skip")
async def process_profile_photo_skip(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await finalize_profile_questionnaire(callback, state, session)

@router.message(FitnessStates.waiting_for_profile_photo, F.photo)
async def process_profile_body_photo(message: Message, state: FSMContext, session: AsyncSession):
    photo = message.photo[-1]
    user_id = message.from_user.id
    user = await session.scalar(select(User).where(User.telegram_id == user_id))
    if user:
        user.photo_file_id = photo.file_id
        await session.commit()
    await finalize_profile_questionnaire(message, state, session)

async def finalize_profile_questionnaire(
    event: Message | CallbackQuery, 
    state: FSMContext, 
    session: AsyncSession
):
    user_id = event.from_user.id
    user = await session.scalar(select(User).where(User.telegram_id == user_id))
    lang = user.language if user and user.language else "uz"
    msg_obj = event if isinstance(event, Message) else event.message
    
    data = await state.get_data()
    goal_val = data.get("profile_goal", "keep_fit")
    weight_val = data.get("profile_weight", 70.0)
    gender_val = data.get("profile_gender", "M")
    height_val = data.get("profile_height", 170.0)
    pending_tool = data.get("pending_tool")
    
    profile = await session.scalar(select(UserFitnessProfile).where(UserFitnessProfile.user_id == user_id))
    if profile:
        profile.height_cm = height_val
        profile.weight_kg = weight_val
        profile.gender = gender_val
        profile.goal = goal_val
        if profile.initial_weight_kg is None:
            profile.initial_weight_kg = weight_val
    else:
        profile = UserFitnessProfile(
            user_id=user_id,
            height_cm=height_val,
            weight_kg=weight_val,
            initial_weight_kg=weight_val,
            gender=gender_val,
            goal=goal_val
        )
        session.add(profile)
    
    initial_log = WeightLog(
        user_id=user_id,
        weight=weight_val
    )
    session.add(initial_log)
    await session.commit()
    
    await msg_obj.answer(texts.PROFILE_SAVED[lang])
    if isinstance(event, CallbackQuery):
        await event.answer()
    
    if pending_tool == "food_calories":
        await state.set_state(FitnessStates.waiting_for_food_photo)
        await msg_obj.answer(texts.CALORIE_PROMPT[lang], reply_markup=get_back_keyboard(lang), parse_mode="HTML")
    elif pending_tool == "ai_coach":
        await state.set_state(FitnessStates.in_ai_nutritionist)
        await state.update_data(history=[])
        await msg_obj.answer(texts.AI_NUTRITIONIST_WELCOME[lang], reply_markup=get_ai_mode_keyboard(lang), parse_mode="HTML")
    elif pending_tool == "meal_plan":
        await state.clear()
        await handle_meal_plan(event, session, state)
    elif pending_tool == "weight_log":
        await state.clear()
        await start_add_weight(event, session, state)
    else:
        await state.clear()
        await show_smart_fitness_hub(event, session, state)

# ======================== 🍎 СЧЁТЧИК КАЛОРИЙ ПО ФОТО ========================

@router.callback_query(F.data == "hub_food_calories")
@router.message(F.text.in_([texts.MENU_BUTTONS["food_calories"]["uz"], texts.MENU_BUTTONS["food_calories"]["ru"]]))
async def start_calorie_counter(event: Message | CallbackQuery, session: AsyncSession, state: FSMContext):
    user, lang, sub = await check_guard_and_get_user(event, session)
    if not user:
        return
        
    msg_obj = event if isinstance(event, Message) else event.message
    profile = await ensure_fitness_profile(event, session, state, "food_calories")
    if not profile:
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    
    await state.set_state(FitnessStates.waiting_for_food_photo)
    await msg_obj.answer(texts.CALORIE_PROMPT[lang], reply_markup=get_back_keyboard(lang), parse_mode="HTML")
    if isinstance(event, CallbackQuery):
        await event.answer()

@router.message(FitnessStates.waiting_for_food_photo, F.text.in_([texts.BACK_BTN["uz"], texts.BACK_BTN["ru"], "◀️ Назад", "◀️ Orqaga", "◀️ Exit"]))
async def cancel_calorie_counter(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    await show_smart_fitness_hub(message, session, state)

@router.message(FitnessStates.waiting_for_food_photo, F.photo)
async def process_food_photo(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user, lang, sub = await check_guard_and_get_user(message, session)
    if not user:
        await state.clear()
        return

    # The guard only read rows. Release its connection before network waits.
    await session.rollback()
    wait_msg = await message.answer(texts.CALORIE_ANALYZING[lang])
    
    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        photo_bytes = io.BytesIO()
        await bot.download_file(file_info.file_path, photo_bytes)
        photo_bytes.seek(0)

        data = await analyze_food_image(
            image_bytes=photo_bytes.read(),
            mime_type="image/jpeg",
            language=lang
        )

        calorie_entry = CalorieLog(
            user_id=message.from_user.id,
            dish=data.get("dish", "Taom"),
            weight_g=data.get("weight_g", 0),
            calories=data.get("calories", 0),
            protein=data.get("protein", 0.0),
            fat=data.get("fat", 0.0),
            carbs=data.get("carbs", 0.0),
            tip=data.get("tip", "")
        )
        session.add(calorie_entry)
        await session.commit()

        # Sum today's total calories
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        start_today = datetime.datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=datetime.timezone.utc)
        
        today_sum_stmt = select(func.sum(CalorieLog.calories)).where(
            CalorieLog.user_id == message.from_user.id,
            CalorieLog.created_at >= start_today
        )
        today_calories = (await session.scalar(today_sum_stmt)) or 0

        card_text = texts.CALORIE_CARD[lang].format(
            dish=html.escape(str(data.get("dish", "-"))),
            weight_g=data.get("weight_g", 0),
            calories=data.get("calories", 0),
            protein=data.get("protein", 0.0),
            fat=data.get("fat", 0.0),
            carbs=data.get("carbs", 0.0),
            tip=html.escape(str(data.get("tip", ""))),
            today_calories=today_calories
        )

        hub_reply_kb = get_smart_fitness_hub_reply_keyboard(lang)
        await wait_msg.delete()
        await message.answer(card_text, reply_markup=hub_reply_kb, parse_mode="HTML")
        await state.clear()
    except Exception as e:
        await wait_msg.delete()
        err_msg = "❌ Ошибка при распознавании фото ИИ. Попробуйте еще раз." if lang == "ru" else "❌ Rasm tahlilida xatolik yuz berdi. Qaytadan urinib ko'ring."
        hub_reply_kb = get_smart_fitness_hub_reply_keyboard(lang)
        await message.answer(err_msg, reply_markup=hub_reply_kb)
        await state.clear()

# ======================== 📋 7 KUNLIK TAOMNOMA & BOZORLIK ========================

@router.callback_query(F.data.in_(["hub_meal_plan", "regen_meal_plan"]))
@router.message(F.text.in_([texts.MENU_BUTTONS["meal_plan"]["uz"], texts.MENU_BUTTONS["meal_plan"]["ru"]]))
async def handle_meal_plan(event: Message | CallbackQuery, session: AsyncSession, state: FSMContext):
    user, lang, sub = await check_guard_and_get_user(event, session)
    if not user:
        return

    msg_obj = event if isinstance(event, Message) else event.message
    profile = await session.scalar(select(UserFitnessProfile).where(UserFitnessProfile.user_id == event.from_user.id))
    
    if not profile:
        await ensure_fitness_profile(event, session, state, "meal_plan")
        if isinstance(event, CallbackQuery):
            await event.answer()
        return

    height_cm = profile.height_cm
    weight_kg = profile.weight_kg
    goal = profile.goal
    gender = profile.gender or "M"
    await session.rollback()
    wait_msg = await msg_obj.answer(texts.MEAL_PLAN_PROMPT[lang], parse_mode="HTML")
    if isinstance(event, CallbackQuery):
        await event.answer()

    try:
        meal_plan_text = await generate_weekly_meal_plan(
            height_cm=height_cm,
            weight_kg=weight_kg,
            goal=goal,
            language=lang,
            gender=gender
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=texts.MEAL_PLAN_REGENERATE_BTN[lang], callback_data="regen_meal_plan")]
        ])

        try:
            await wait_msg.delete()
        except Exception:
            pass

        chunks = split_text_into_chunks(meal_plan_text, max_chunk_size=3500)
        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            markup = kb if is_last else None
            await send_safe_message(msg_obj, chunk, reply_markup=markup)

    except Exception as e:
        try:
            await wait_msg.delete()
        except Exception:
            pass
        logger.exception("Meal plan generation failed for user %s", event.from_user.id)
        err_text = "❌ Taomnoma yaratishda xatolik. Keyinroq urinib ko'ring." if lang == "uz" else "❌ Ошибка генерации рациона. Попробуйте позже."
        await msg_obj.answer(err_text)

# ======================== 🥗 RUXSAT VA TAQIQLANGAN MAHSULOTLAR ========================

@router.callback_query(F.data == "hub_allowed_foods")
@router.message(F.text.in_([texts.MENU_BUTTONS["allowed_foods"]["uz"], texts.MENU_BUTTONS["allowed_foods"]["ru"]]))
async def handle_allowed_foods(event: Message | CallbackQuery, session: AsyncSession):
    user, lang, sub = await check_guard_and_get_user(event, session)
    if not user:
        return

    text = texts.ALLOWED_FORBIDDEN_TEXT[lang]
    reply_kb = get_smart_fitness_hub_reply_keyboard(lang)

    if isinstance(event, CallbackQuery):
        await event.message.answer(text, reply_markup=reply_kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=reply_kb, parse_mode="HTML")

# ======================== 🏋️‍♂️ ДНЕВНИК ВЕСА И ГРАФИК ========================

@router.callback_query(F.data == "hub_weight_menu")
@router.message(F.text.in_([texts.MENU_BUTTONS["weight_log"]["uz"], texts.MENU_BUTTONS["weight_log"]["ru"]]))
async def show_weight_submenu(event: Message | CallbackQuery, session: AsyncSession):
    user, lang, sub = await check_guard_and_get_user(event, session)
    if not user:
        return

    text = texts.WEIGHT_SUBMENU_TEXT[lang]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=texts.WEIGHT_ADD_BTN[lang], callback_data="hub_add_weight"),
            InlineKeyboardButton(text=texts.WEIGHT_CHART_BTN[lang], callback_data="hub_show_chart")
        ]
    ])

    if isinstance(event, CallbackQuery):
        await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "hub_add_weight")
async def start_add_weight(event: Message | CallbackQuery, session: AsyncSession, state: FSMContext):
    user, lang, sub = await check_guard_and_get_user(event, session)
    if not user:
        return

    profile = await ensure_fitness_profile(event, session, state, "weight_log")
    if not profile:
        if isinstance(event, CallbackQuery):
            await event.answer()
        return

    await state.set_state(FitnessStates.waiting_for_weight)
    msg_obj = event if isinstance(event, Message) else event.message
    await msg_obj.answer(texts.WEIGHT_PROMPT[lang], reply_markup=get_back_keyboard(lang), parse_mode="HTML")
    if isinstance(event, CallbackQuery):
        await event.answer()

@router.callback_query(F.data == "hub_show_chart")
async def cb_show_weight_chart(callback: CallbackQuery, session: AsyncSession):
    user, lang, sub = await check_guard_and_get_user(callback, session)
    if not user:
        return

    stmt = select(WeightLog).where(
        WeightLog.user_id == callback.from_user.id
    ).order_by(WeightLog.recorded_at.asc())
    
    result = await session.execute(stmt)
    records = result.scalars().all()

    if not records:
        await callback.message.answer(texts.WEIGHT_NO_DATA[lang])
        await callback.answer()
        return

    record_tuples = [(r.recorded_at, r.weight) for r in records]
    await session.rollback()
    await callback.answer()

    try:
        # Queue renders on the loop, keeping executor threads free for I/O.
        async with _chart_render_semaphore:
            buf, summary_text = await asyncio.to_thread(generate_weight_chart, record_tuples, language=lang)
        with buf:
            input_file = BufferedInputFile(buf.getvalue(), filename="weight_chart.png")
        await callback.message.answer_photo(photo=input_file, caption=summary_text)
    except Exception as e:
        logger.exception("Weight chart failed for user %s", callback.from_user.id)
        err_text = "❌ Ошибка построения графика. Попробуйте позже." if lang == "ru" else "❌ Grafik yaratishda xatolik. Keyinroq urinib ko'ring."
        await callback.message.answer(err_text)

@router.message(FitnessStates.waiting_for_weight, F.text.in_([texts.BACK_BTN["uz"], texts.BACK_BTN["ru"], "◀️ Назад", "◀️ Orqaga", "◀️ Exit"]))
async def cancel_weight_log(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    await show_smart_fitness_hub(message, session, state)

@router.message(FitnessStates.waiting_for_weight)
async def process_weight_input(message: Message, state: FSMContext, session: AsyncSession):
    user, lang, sub = await check_guard_and_get_user(message, session)
    if not user:
        await state.clear()
        return

    raw_text = (message.text or "").strip().replace(",", ".")
    try:
        weight_val = float(raw_text)
        if not math.isfinite(weight_val) or weight_val <= 0 or weight_val > 300:
            raise ValueError("Invalid weight range")
    except ValueError:
        await message.answer(texts.WEIGHT_INVALID[lang])
        return

    log_entry = WeightLog(
        user_id=message.from_user.id,
        weight=weight_val
    )
    session.add(log_entry)

    prof = await session.scalar(select(UserFitnessProfile).where(UserFitnessProfile.user_id == message.from_user.id))
    if prof:
        prof.weight_kg = weight_val
        if prof.initial_weight_kg is None:
            prof.initial_weight_kg = weight_val

    await session.commit()

    hub_reply_kb = get_smart_fitness_hub_reply_keyboard(lang)
    await message.answer(
        texts.WEIGHT_SAVED[lang].format(weight=weight_val),
        reply_markup=hub_reply_kb,
        parse_mode="HTML"
    )
    await state.clear()

# ======================== 🤖 КАРМАННЫЙ НУТРИЦИОЛОГ (GEMINI AI) ========================

@router.callback_query(F.data == "hub_ai_coach")
@router.message(F.text.in_([texts.MENU_BUTTONS["ai_coach"]["uz"], texts.MENU_BUTTONS["ai_coach"]["ru"]]))
async def start_ai_nutritionist(event: Message | CallbackQuery, session: AsyncSession, state: FSMContext):
    user, lang, sub = await check_guard_and_get_user(event, session)
    if not user:
        return

    msg_obj = event if isinstance(event, Message) else event.message
    profile = await ensure_fitness_profile(event, session, state, "ai_coach")
    if not profile:
        if isinstance(event, CallbackQuery):
            await event.answer()
        return

    await state.set_state(FitnessStates.in_ai_nutritionist)
    await state.update_data(history=[])
    await msg_obj.answer(texts.AI_NUTRITIONIST_WELCOME[lang], reply_markup=get_ai_mode_keyboard(lang), parse_mode="HTML")
    if isinstance(event, CallbackQuery):
        await event.answer()

@router.message(FitnessStates.in_ai_nutritionist, F.text.in_([
    texts.AI_EXIT_BTN["uz"], texts.AI_EXIT_BTN["ru"], 
    "◀️ Выйти из режима ИИ", "◀️ Exit / Chiqish", "◀️ Exit", "◀️ Назад", "◀️ Orqaga", "/cancel"
]))
async def exit_ai_nutritionist(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    await show_smart_fitness_hub(message, session, state)

@router.message(FitnessStates.in_ai_nutritionist, F.text)
async def process_ai_nutritionist_query(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user, lang, sub = await check_guard_and_get_user(message, session)
    if not user:
        await state.clear()
        return

    data = await state.get_data()
    history = data.get("history", [])

    prof_row = await session.scalar(select(UserFitnessProfile).where(UserFitnessProfile.user_id == message.from_user.id))
    prof_dict = None
    if prof_row:
        goal_lbl = texts.GOAL_OPTIONS.get(prof_row.goal, {}).get(lang, prof_row.goal)
        gender_lbl = texts.GENDER_OPTIONS.get(prof_row.gender, {}).get(lang, prof_row.gender or "M")
        prof_dict = {
            "gender": gender_lbl,
            "height_cm": prof_row.height_cm,
            "weight_kg": prof_row.weight_kg,
            "goal": goal_lbl
        }

    await session.rollback()
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        response_text = await ask_nutritionist_ai(
            history=history,
            user_message=message.text,
            language=lang,
            profile=prof_dict
        )

        history.append({"role": "user", "content": message.text})
        history.append({"role": "model", "content": response_text})

        if len(history) > 20:
            history = history[-20:]

        await state.update_data(history=history)
        for chunk in split_text_into_chunks(response_text):
            await send_safe_message(message, chunk, reply_markup=get_ai_mode_keyboard(lang))

    except Exception as e:
        err_msg = "❌ Произошла ошибка при обращении к ИИ. Попробуйте еще раз позже." if lang == "ru" else "❌ ИИ bilan bog'lanishda xatolik yuz berdi. Keyinroq qaytadan urinib ko'ring."
        await message.answer(err_msg, reply_markup=get_ai_mode_keyboard(lang))
