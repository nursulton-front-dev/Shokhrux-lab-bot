import datetime
import csv
import os
import asyncio
from io import StringIO
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc

from bot.database.models import User, Subscription, Payment
from bot.filters.admin import IsAdmin
from bot.states.admin import AdminBroadcast, AdminUserSearch
from bot.config import config

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

def get_channel_id() -> int:
    return config.channel_id or int(os.getenv("CHANNEL_ID", "-1001234567890"))

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

def get_admin_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Касса за сегодня"), KeyboardButton(text="📊 Отчёт за месяц")],
            [KeyboardButton(text="🌐 За всё время"), KeyboardButton(text="🔄 Продления (Retention)")],
            [KeyboardButton(text="👥 Поиск клиента"), KeyboardButton(text="📢 Рассылка сообщений")],
            [KeyboardButton(text="📥 Скачать Excel"), KeyboardButton(text="📖 Руководство")],
        ],
        resize_keyboard=True
    )

@router.message(Command("admin"))
@router.message(CommandStart())
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("👑 <b>Центр управления ботом</b>\nВыберите раздел в меню ниже 👇", reply_markup=get_admin_main_kb())

@router.message(F.text == "👑 Главное меню")
async def msg_admin_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("👑 <b>Центр управления ботом</b>\nВыберите раздел:", reply_markup=get_admin_main_kb())

@router.callback_query(F.data == "admin_main")
async def cb_admin_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("👑 <b>Центр управления ботом</b>\nВыберите раздел:", reply_markup=get_admin_main_kb())
    await callback.answer()

@router.message(F.text == "📖 Руководство")
async def msg_admin_guide(message: Message):
    text = (
        "📖 <b>ПОЛНОЕ РУКОВОДСТВО ПО АДМИН-ПАНЕЛИ</b>\n\n"
        "Добро пожаловать в центр управления ботом закрытого канала!\n\n"
        "--- \n"
        "1. 📊 <b>АНАЛИТИКА И ФИНАНСЫ</b>\n"
        "• Нажмите «📊 Аналитика» для просмотра свежих метрик:\n"
        "  - Выручка (За день, месяц, всё время).\n"
        "  - Конверсия пользователей из старта в покупку.\n"
        "• Нажмите «📥 Скачать отчёт», чтобы получить полные транзакции в Excel/CSV.\n\n"
        "--- \n"
        "2. 👤 <b>УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ</b>\n"
        "• Нажмите «🔍 Найти пользователя» и введите его Telegram ID или @username.\n"
        "• В карточке пользователя вы можете:\n"
        "  - ➕ Начислить/Продлить подписку вручную (например, если клиент перевел на карту напрямую).\n"
        "  - ⛔️ Аннулировать подписку (бот автоматически кикнет его из канала).\n"
        "  - 🔗 Сгенерировать индивидуальную одноразовую ссылку.\n\n"
        "--- \n"
        "3. 📢 <b>МОДУЛЬ РАССЫЛКИ (МАРКЕТИНГ)</b>\n"
        "1. Нажмите «📢 Создать рассылку».\n"
        "2. Выберите аудиторию:\n"
        "   - Все пользователи.\n"
        "   - Только АКТИВНЫЕ подписчики.\n"
        "   - ИСТЕКШИЕ (у кого кончилась подписка — идеальная база для возврата).\n"
        "   - НЕ ПОКУПАВШИЕ (кто нажал /start, но не купил — отправьте им скидку!).\n"
        "3. Отправьте боту пост (текст, фото, видео, кнопки).\n"
        "4. Нажмите «👁 Предпросмотр», проверьте пост и затем жмите «🚀 Запустить рассылку».\n\n"
        "--- \n"
        "4. 🗄️ <b>БАЗА ДАННЫХ И БЭКАПЫ</b>\n"
        "• Раздел «🗄️ База данных» показывает количество записей в БД.\n"
        "• Нажимайте «💾 Скачать бэкап» раз в неделю, чтобы сохранить файл со всей базой пользователей прямо в чат.\n\n"
        "--- \n"
        "⚡️ ВАЖНО:\n"
        "Бот работает в режиме 24/7. Все ссылки на канал создаются ОДНОРАЗОВЫМИ, чтобы исключить слив и передачу ссылок третьим лицам."
    )
    await message.answer(text)

# ======================== АНАЛИТИКА ========================
def get_analytics_submenu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 За сегодня", callback_data="an_today"), InlineKeyboardButton(text="📊 За текущий месяц", callback_data="an_month")],
        [InlineKeyboardButton(text="🌐 За всё время", callback_data="an_all"), InlineKeyboardButton(text="🔄 Когорты / Retention", callback_data="an_cohorts")],
        [InlineKeyboardButton(text="📥 Скачать Excel", callback_data="an_report")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="an_close")]
    ])

@router.message(F.text == "📊 Аналитика")
async def msg_admin_stats(message: Message):
    await message.answer("📊 <b>Модуль Аналитики</b>\nВыберите нужный отчет:", reply_markup=get_analytics_submenu())

@router.callback_query(F.data == "an_close")
async def cb_an_close(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()

async def get_financial_report(session: AsyncSession, period_name: str, start_date=None):
    # Base query for completed payments
    stmt = select(Payment).where(Payment.status == 'completed')
    if start_date:
        stmt = stmt.where(Payment.created_at >= start_date)
        
    res = await session.execute(stmt)
    payments = res.scalars().all()
    
    total_rev = 0
    total_sales = len(payments)
    t1_qty, t1_sum = 0, 0
    t3_qty, t3_sum = 0, 0
    t6_qty, t6_sum = 0, 0
    
    for p in payments:
        total_rev += p.amount
        if p.tariff_months == 1:
            t1_qty += 1
            t1_sum += p.amount
        elif p.tariff_months == 3:
            t3_qty += 1
            t3_sum += p.amount
        elif p.tariff_months == 6:
            t6_qty += 1
            t6_sum += p.amount
            
    text = (
        f"📋 <b>Финансовый отчет ({period_name}):</b>\n\n"
        f"💵 <b>Общая касса:</b> {total_rev:,.0f} UZS\n"
        f"🛍 <b>Всего продаж:</b> {total_sales} шт.\n\n"
        f"📦 <b>Разбивка по тарифам:</b>\n"
        f"• 1 месяц (500k): <b>{t1_qty} шт.</b> ({t1_sum:,.0f} UZS)\n"
        f"• 3 месяца (1.2m): <b>{t3_qty} шт.</b> ({t3_sum:,.0f} UZS)\n"
        f"• 6 месяцев (2.3m): <b>{t6_qty} шт.</b> ({t6_sum:,.0f} UZS)\n"
    )
    return text

@router.callback_query(F.data == "an_today")
async def cb_an_today(callback: CallbackQuery, session: AsyncSession):
    now = datetime.datetime.now(datetime.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    text = await get_financial_report(session, "📅 За сегодня", today_start)
    
    # Add new users count
    new_users = await session.scalar(select(func.count()).where(User.created_at >= today_start).select_from(User))
    text += f"\n🆕 <b>Новых пользователей:</b> {new_users} чел."
    
    await callback.message.edit_text(text, reply_markup=get_analytics_submenu())
    await callback.answer()

@router.callback_query(F.data == "an_month")
async def cb_an_month(callback: CallbackQuery, session: AsyncSession):
    now = datetime.datetime.now(datetime.timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    text = await get_financial_report(session, "📊 За текущий месяц", month_start)
    await callback.message.edit_text(text, reply_markup=get_analytics_submenu())
    await callback.answer()

@router.callback_query(F.data == "an_all")
async def cb_an_all(callback: CallbackQuery, session: AsyncSession):
    text = await get_financial_report(session, "🌐 За всё время")
    await callback.message.edit_text(text, reply_markup=get_analytics_submenu())
    await callback.answer()

# 2. 🔄 Когорты & Retention (an_cohorts)
@router.callback_query(F.data == "an_cohorts")
async def cb_an_cohorts(callback: CallbackQuery, session: AsyncSession):
    await callback.answer("Расчет когорт...", show_alert=False)
    # Fetch all completed payments ordered by user and date
    stmt = select(Payment.user_id, Payment.created_at).where(Payment.status == 'completed').order_by(Payment.user_id, Payment.created_at)
    res = await session.execute(stmt)
    payments = res.all()
    
    # Process in memory
    cohorts = {} # key: YYYY-MM, value: dict(users=set(), m1=set(), m2=set())
    user_cohort = {}
    
    for uid, created_at in payments:
        month_str = created_at.strftime("%Y-%m")
        if uid not in user_cohort:
            user_cohort[uid] = month_str
            if month_str not in cohorts:
                cohorts[month_str] = {'users': set(), 'm1': set(), 'm2': set()}
            cohorts[month_str]['users'].add(uid)
        else:
            c_month = user_cohort[uid]
            # calculate diff in months
            c_date = datetime.datetime.strptime(c_month, "%Y-%m")
            diff_months = (created_at.year - c_date.year) * 12 + created_at.month - c_date.month
            if diff_months == 1:
                cohorts[c_month]['m1'].add(uid)
            elif diff_months >= 2:
                cohorts[c_month]['m2'].add(uid)
                
    text = "🔄 <b>Когортный анализ & Retention</b>\n\n"
    if not cohorts:
        text += "Нет данных для анализа."
    
    for c_month in sorted(cohorts.keys())[-5:]: # show last 5 cohorts
        total = len(cohorts[c_month]['users'])
        m1 = len(cohorts[c_month]['m1'])
        m2 = len(cohorts[c_month]['m2'])
        
        m1_pct = (m1 / total * 100) if total else 0
        m2_pct = (m2 / total * 100) if total else 0
        churn = 100 - m1_pct
        
        text += (f"📅 <b>Когорта {c_month}</b> ({total} чел)\n"
                 f"↳ M1 (2-й мес): {m1} чел ({m1_pct:.1f}%)\n"
                 f"↳ M2+ (3-й мес+): {m2} чел ({m2_pct:.1f}%)\n"
                 f"💔 Churn Rate (отток на 2-й мес): {churn:.1f}%\n\n")
                 
    await callback.message.edit_text(text, reply_markup=get_analytics_submenu())
    await callback.answer()

# 5. 📥 Скачать Excel-отчет (an_report)
@router.callback_query(F.data == "an_report")
async def cb_an_report_dl(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    await callback.answer("Генерация детального отчета...", show_alert=False)
    
    # We need: User ID | Username | Дата первой оплаты | Текущий статус | Кол-во продлений | LTV (Сумма) | Дата окончания | Когорта
    stmt = select(User, Subscription).outerjoin(Subscription, User.telegram_id == Subscription.user_id).order_by(User.telegram_id)
    res = await session.execute(stmt)
    rows = res.all()
    
    # We also need payments to calculate LTV and First payment
    p_stmt = select(Payment).where(Payment.status == 'completed').order_by(Payment.created_at)
    p_res = await session.execute(p_stmt)
    payments = p_res.scalars().all()
    
    user_stats = {}
    for p in payments:
        if p.user_id not in user_stats:
            user_stats[p.user_id] = {'first_date': p.created_at, 'ltv': 0, 'count': 0}
        user_stats[p.user_id]['ltv'] += p.amount
        user_stats[p.user_id]['count'] += 1
        
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['User ID', 'Username', 'Дата первой оплаты', 'Текущий статус', 'Кол-во покупок', 'LTV (UZS)', 'Дата окончания', 'Когорта'])
    
    processed_users = set()
    for user, sub in rows:
        if user.telegram_id in processed_users:
            continue
        processed_users.add(user.telegram_id)
        
        stats = user_stats.get(user.telegram_id, None)
        if not stats:
            continue
            
        first_date = stats['first_date'].strftime("%Y-%m-%d")
        cohort = stats['first_date'].strftime("%Y-%m")
        ltv = stats['ltv']
        buys = stats['count']
        
        status = "ACTIVE" if sub and sub.status == 'active' and sub.expires_at > datetime.datetime.now(datetime.timezone.utc) else "EXPIRED"
        expires = sub.expires_at.strftime("%Y-%m-%d") if sub and sub.expires_at else "-"
        
        writer.writerow([user.telegram_id, user.username or "", first_date, status, buys, ltv, expires, cohort])
        
    csv_bytes = output.getvalue().encode('utf-8')
    input_file = BufferedInputFile(csv_bytes, filename=f"marketing_report_{datetime.datetime.now().strftime('%Y%m%d')}.csv")
    
    await bot.send_document(chat_id=callback.from_user.id, document=input_file, caption="📥 Детальный маркетинговый отчет (Покупатели)")

# ======================== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ========================
@router.message(F.text == "🔍 Найти пользователя")
async def msg_search_user(message: Message, state: FSMContext):
    await message.answer(
        "🔍 <b>Найти пользователя</b>\n\n"
        "Отправьте мне Telegram ID пользователя или его @username (без собачки).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_main")]])
    )
    await state.set_state(AdminUserSearch.waiting_for_query)

@router.message(AdminUserSearch.waiting_for_query)
async def process_user_search(message: Message, state: FSMContext, session: AsyncSession):
    query = message.text.strip()
    
    if query.isdigit():
        stmt = select(User).where(User.telegram_id == int(query))
    else:
        query = query.replace("@", "")
        stmt = select(User).where(User.username.ilike(f"%{query}%"))
        
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        await message.answer("❌ Пользователь не найден. Попробуйте еще раз или нажмите /admin")
        return
        
    # Get active sub
    sub_stmt = select(Subscription).where(
        Subscription.user_id == user.telegram_id,
        Subscription.status == "active"
    ).order_by(Subscription.expires_at.desc()).limit(1)
    sub_res = await session.execute(sub_stmt)
    sub = sub_res.scalar_one_or_none()
    
    now = datetime.datetime.now(datetime.timezone.utc)
    if sub and sub.expires_at > now:
        status = "✅ АКТИВНА"
        expires = sub.expires_at.strftime("%Y-%m-%d %H:%M UTC")
    else:
        status = "❌ ИСТЕКЛА / НЕТ"
        expires = "-"
        
    text = (
        f"👤 <b>Карточка пользователя</b>\n\n"
        f"ID: <code>{user.telegram_id}</code>\n"
        f"Username: @{user.username or 'Нет'}\n"
        f"Имя: {user.full_name or 'Нет'}\n"
        f"Телефон: {user.phone_number or 'Нет'}\n\n"
        f"<b>Подписка:</b> {status}\n"
        f"<b>Истекает:</b> {expires}\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Продлить (30 дней)", callback_data=f"adm_user_ext_{user.telegram_id}")],
        [InlineKeyboardButton(text="⛔️ Аннулировать (Кик)", callback_data=f"adm_user_kick_{user.telegram_id}")],
        [InlineKeyboardButton(text="🔗 Сгенерировать ссылку", callback_data=f"adm_user_link_{user.telegram_id}")],
        [InlineKeyboardButton(text="◀️ В меню", callback_data="admin_main")]
    ])
    
    await message.answer(text, reply_markup=keyboard)
    await state.clear()

@router.callback_query(F.data.startswith("adm_user_ext_"))
async def adm_user_extend(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[3])
    
    sub_stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.status == "active"
    ).order_by(Subscription.expires_at.desc()).limit(1)
    sub_res = await session.execute(sub_stmt)
    sub = sub_res.scalar_one_or_none()
    
    now = datetime.datetime.now(datetime.timezone.utc)
    if sub and sub.expires_at > now:
        started_at = sub.expires_at
    else:
        started_at = now
        
    expires_at = started_at + datetime.timedelta(days=30)
    
    new_sub = Subscription(
        user_id=user_id,
        status="active",
        tariff_months=1,
        started_at=started_at,
        expires_at=expires_at
    )
    session.add(new_sub)
    await session.commit()
    
    await callback.answer("✅ Подписка продлена на 30 дней!", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="admin_main")]]))

@router.callback_query(F.data.startswith("adm_user_kick_"))
async def adm_user_kick(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = int(callback.data.split("_")[3])
    
    sub_stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.status == "active"
    )
    sub_res = await session.execute(sub_stmt)
    subs = sub_res.scalars().all()
    
    for sub in subs:
        sub.status = "expired"
    await session.commit()
    
    try:
        channel_id = get_channel_id()
        await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
        await bot.unban_chat_member(chat_id=channel_id, user_id=user_id)
        await callback.answer("⛔️ Подписка аннулирована, пользователь кикнут.", show_alert=True)
    except Exception as e:
        await callback.answer(f"Подписка отменена, но кикнуть не удалось: {e}", show_alert=True)
        
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="admin_main")]]))

@router.callback_query(F.data.startswith("adm_user_link_"))
async def adm_user_link(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split("_")[3])
    try:
        channel_id = get_channel_id()
        invite_link = await bot.create_chat_invite_link(
            chat_id=channel_id,
            member_limit=1,
            name=f"Manual: {user_id}"
        )
        await callback.message.answer(f"🔗 <b>Одноразовая ссылка для ID {user_id}:</b>\n{invite_link.invite_link}")
        await callback.answer()
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

# ======================== МОДУЛЬ РАССЫЛКИ ========================
@router.message(F.text == "📢 Создать рассылку")
async def msg_admin_broadcast(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Все пользователи", callback_data="bcast_all")],
        [InlineKeyboardButton(text="Только АКТИВНЫЕ", callback_data="bcast_active")],
        [InlineKeyboardButton(text="ИСТЕКШИЕ", callback_data="bcast_expired")],
        [InlineKeyboardButton(text="НЕ ПОКУПАВШИЕ", callback_data="bcast_never")],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_main")]
    ])
    await message.answer("📢 <b>Создать рассылку</b>\n\nВыберите аудиторию:", reply_markup=keyboard)
    await state.set_state(AdminBroadcast.waiting_for_audience)

@router.callback_query(AdminBroadcast.waiting_for_audience, F.data.startswith("bcast_"))
async def process_bcast_audience(callback: CallbackQuery, state: FSMContext):
    audience = callback.data.split("_")[1]
    await state.update_data(audience=audience)
    
    await callback.message.edit_text(
        "Отправьте мне пост для рассылки (Текст, Фото, Видео, Кружок).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_main")]])
    )
    await state.set_state(AdminBroadcast.waiting_for_message)
    await callback.answer()

@router.message(AdminBroadcast.waiting_for_message)
async def process_bcast_msg(message: Message, state: FSMContext):
    await state.update_data(msg_id=message.message_id, chat_id=message.chat.id)
    
    data = await state.get_data()
    audience = data.get("audience")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁 Предпросмотр", callback_data="bcast_preview")],
        [InlineKeyboardButton(text="🚀 Запустить рассылку", callback_data="bcast_run")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_main")]
    ])
    
    await message.answer(f"Пост сохранен. Аудитория: <b>{audience}</b>\nЧто делаем дальше?", reply_markup=keyboard)
    await state.set_state(AdminBroadcast.waiting_for_confirm)

@router.callback_query(AdminBroadcast.waiting_for_confirm, F.data == "bcast_preview")
async def cb_bcast_preview(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await bot.copy_message(
        chat_id=callback.from_user.id,
        from_chat_id=data['chat_id'],
        message_id=data['msg_id']
    )
    await callback.answer()

@router.callback_query(AdminBroadcast.waiting_for_confirm, F.data == "bcast_run")
async def cb_bcast_run(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    audience = data['audience']
    
    # Logic to fetch user IDs based on audience
    now = datetime.datetime.now(datetime.timezone.utc)
    
    if audience == "all":
        stmt = select(User.telegram_id)
    elif audience == "active":
        stmt = select(func.distinct(Subscription.user_id)).where(Subscription.status == "active", Subscription.expires_at > now)
    elif audience == "expired":
        # Expired but not currently active
        sub_query = select(Subscription.user_id).where(Subscription.status == "active", Subscription.expires_at > now)
        stmt = select(func.distinct(Subscription.user_id)).where(Subscription.status == "expired", Subscription.user_id.notin_(sub_query))
    elif audience == "never":
        # Users without any completed payment
        sub_query = select(Payment.user_id).where(Payment.status == "completed")
        stmt = select(User.telegram_id).where(User.telegram_id.notin_(sub_query))
    else:
        stmt = select(User.telegram_id)
        
    result = await session.execute(stmt)
    user_ids = result.scalars().all()
    
    await callback.message.edit_text(f"🚀 <b>Рассылка запущена!</b> Ожидайте окончания...\nАудитория: {len(user_ids)} чел.")
    
    async def do_broadcast(uids, from_chat, msg_id):
        sent = 0
        for uid in uids:
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=from_chat, message_id=msg_id)
                sent += 1
                await asyncio.sleep(0.05) # Prevent flood
            except Exception:
                pass
        try:
            await bot.send_message(chat_id=callback.from_user.id, text=f"✅ <b>Рассылка завершена!</b>\nУспешно доставлено: {sent} / {len(uids)}.")
        except:
            pass

    # Fire and forget (in production, use task queues like Celery/Redis)
    asyncio.create_task(do_broadcast(user_ids, data['chat_id'], data['msg_id']))
    await state.clear()
    await callback.answer()

# ======================== БАЗА ДАННЫХ ========================
@router.message(F.text == "🗄️ База данных")
async def msg_admin_db(message: Message, session: AsyncSession):
    u_count = await session.scalar(select(func.count()).select_from(User))
    s_count = await session.scalar(select(func.count()).select_from(Subscription))
    p_count = await session.scalar(select(func.count()).select_from(Payment))
    
    text = (
        f"🗄️ <b>БАЗА ДАННЫХ</b>\n\n"
        f"• Пользователи: <b>{u_count}</b>\n"
        f"• Подписки: <b>{s_count}</b>\n"
        f"• Платежи: <b>{p_count}</b>\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 Скачать бэкап", callback_data="admin_db_backup")]
    ])
    await message.answer(text, reply_markup=keyboard)

@router.callback_query(F.data == "admin_db_backup")
async def cb_admin_db_backup(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    await callback.answer("Бэкап генерируется...", show_alert=False)
    
    stmt = select(User)
    result = await session.execute(stmt)
    users = result.scalars().all()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['telegram_id', 'full_name', 'username', 'phone', 'created_at'])
    
    for u in users:
        writer.writerow([u.telegram_id, u.full_name, u.username, u.phone_number, u.created_at])
        
    csv_bytes = output.getvalue().encode('utf-8')
    input_file = BufferedInputFile(csv_bytes, filename=f"database_backup_{datetime.datetime.now().strftime('%Y%m%d')}.csv")
    
    await bot.send_document(chat_id=callback.from_user.id, document=input_file, caption="🗄️ Резервная копия базы пользователей (CSV)")

# ======================== ЗАЯВКИ (MANUAL PAYMENTS) ========================
@router.message(F.text == "⏳ Заявки на оплату")
async def msg_admin_pending_payments(message: Message, session: AsyncSession):
    stmt = select(Payment).where(Payment.status == "pending").limit(10)
    result = await session.execute(stmt)
    payments = result.scalars().all()
    
    if not payments:
        await message.answer("✅ Нет новых заявок на оплату.")
        return

    text = "⏳ <b>Последние 10 заявок:</b>\n\n"
    for p in payments:
        text += f"ID: <b>{p.id}</b> | Сумма: {p.amount:,} UZS | User: <code>{p.user_id}</code>\n"
        
    text += "\n<i>(Чтобы подтвердить заявку, используйте кнопки, которые пришли вам отдельным сообщением при оформлении заявки клиентом)</i>"
    
    await message.answer(text)

@router.callback_query(F.data.startswith("admin_conf_"))
async def admin_confirm_payment(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    _, _, payment_id_str, user_id_str = callback.data.split("_")
    payment_id = int(payment_id_str)
    user_id = int(user_id_str)
    
    stmt = select(Payment).where(Payment.id == payment_id)
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()
    
    if payment and payment.status == "pending":
        payment.status = "completed"
        
        # Extension
        sub_stmt = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status == "active"
        ).order_by(Subscription.expires_at.desc()).limit(1)
        sub_res = await session.execute(sub_stmt)
        current_sub = sub_res.scalar_one_or_none()
        
        now = datetime.datetime.now(datetime.timezone.utc)
        tariff_days = payment.tariff_months * 30
        
        if current_sub and current_sub.expires_at > now:
            started_at = current_sub.expires_at
        else:
            started_at = now
            
        expires_at = started_at + datetime.timedelta(days=tariff_days)
            
        new_sub = Subscription(
            user_id=user_id,
            status="active",
            tariff_months=payment.tariff_months,
            started_at=started_at,
            expires_at=expires_at
        )
        session.add(new_sub)
        await session.commit()
        
        await callback.message.edit_text(callback.message.html_text + f"\n\n✅ <b>Одобрено.</b>")
        
        try:
            channel_id = get_channel_id()
            invite_link = await bot.create_chat_invite_link(
                chat_id=channel_id,
                member_limit=1,
                name=f"Sub: {user_id} ({payment.tariff_months}mo)"
            )
            user_msg = (
                f"🎉 <b>Tabriklaymiz! To'lov muvaffaqiyatli amalga oshirildi.</b>\n\n"
                f"Siz yangi, sog'lom va ko'rkam tanangiz sari birinchi muhim qadamni tashladingiz! 💪\n\n"
                f"🔑 <b>Sizning shaxsiy taklifnoma havolangiz:</b>\n\n"
                f"{invite_link.invite_link}\n\n"
                f"⚠️ Diqqat: Bu havola bir martalik bo'lib, faqat siz uchun yaratilgan. Uni boshqalarga uzatmang!\n\n"
                f"📅 Obuna tugash sanasi: {expires_at.strftime('%Y-%m-%d %H:%M UTC')}"
            )
            await bot.send_message(chat_id=user_id, text=user_msg)
        except Exception as e:
            await bot.send_message(chat_id=user_id, text=f"✅ To'lov tasdiqlandi, ammo kanal havolasini yaratishda xatolik yuz berdi. Iltimos, admin bilan bog'laning.")

    else:
        await callback.message.edit_text("Заявка не найдена или уже обработана.")
    await callback.answer()

@router.callback_query(F.data.startswith("admin_rej_"))
async def admin_reject_payment(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    _, _, payment_id_str, user_id_str = callback.data.split("_")
    payment_id = int(payment_id_str)
    user_id = int(user_id_str)
    
    stmt = select(Payment).where(Payment.id == payment_id)
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()
    
    if payment and payment.status == "pending":
        payment.status = "failed"
        await session.commit()
        
        await callback.message.edit_text(callback.message.html_text + "\n\n❌ <b>Отклонено.</b>")
        try:
            await bot.send_message(chat_id=user_id, text="❌ <b>Sizning to'lovingiz rad etildi.</b> Iltimos, ma'lumotlarni tekshirib qaytadan urinib ko'ring yoki admin bilan bog'laning.")
        except:
            pass
    else:
        await callback.message.edit_text("Заявка не найдена или уже обработана.")
    await callback.answer()
