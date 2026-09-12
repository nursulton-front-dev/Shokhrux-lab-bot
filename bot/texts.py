RESIDENT_WELCOME = {
    "uz": "✅ <b>Siz allaqachon klub a'zosisiz!</b>\n\n📊 Status: <b>{status}</b>\n📅 Obuna tugashi: <b>{expires_at}</b> (Toshkent)\n\nKerakli bo'limni tanlang 👇",
    "ru": "✅ <b>Вы уже участник клуба!</b>\n\n📊 Статус: <b>{status}</b>\n📅 Подписка до: <b>{expires_at}</b> (Ташкент)\n\nВыберите раздел 👇",
}
TRAINING_ACCESS = {
    "uz": "🏋️ Mashg'ulotlar yopiq klub kanalida. Shaxsiy havolangiz orqali kiring:",
    "ru": "🏋️ Тренировки находятся в закрытом канале клуба. Войдите по своей ссылке:",
}
TRAINING_ACCESS_PENDING = {
    "uz": "⏳ Kirish havolasi tayyorlanmoqda. Bot uni avtomatik yuboradi. Havola kelmasa, yordam xizmatiga yozing.",
    "ru": "⏳ Ссылка доступа готовится. Бот отправит её автоматически. Если ссылка не приходит, напишите в поддержку.",
}

WELCOME_TEXT = {
    'uz': (
        '👋 Assalomu alaykum!\n'
        '\n'
        'Yopiq Telegram kanalimizga xush kelibsiz 💪\n'
        '\n'
        'Bu yerda natijaga erishish uchun hamma narsa bir joyda:\n'
        '\n'
        '🏋️ Mashg‘ulotlar\n'
        '🥗 Ovqatlanish va dieta\n'
        '😴 Uyqu va rejim\n'
        '💪 Massa olish va ozish\n'
        '💊 Farmakologiya\n'
        '🤖 BJU va ovqatlanish uchun AI\n'
        '📞 Guruhli qo‘ng‘iroqlar va uchrashuvlar\n'
        '\n'
        'Tarifni tanlang va natija sari harakatni boshlang 🔥'
    ),
    'ru': (
        '👋 Ассаламу алейкум!\n'
        '\n'
        'Добро пожаловать в закрытый Telegram-канал 💪\n'
        '\n'
        'Здесь всё для твоего результата в одном месте:\n'
        '\n'
        '🏋️ Тренировки\n'
        '🥗 Питание и диета\n'
        '😴 Сон и режим\n'
        '💪 Набор массы и похудение\n'
        '💊 Фармакология\n'
        '🤖 ИИ для расчёта БЖУ и питания\n'
        '📞 Созвоны и встречи с участниками\n'
        '\n'
        'Выбирай тариф и начинай работать над результатом 🔥'
    ),
}

PROFILE_TEXT = {
    "uz": (
        "👤 <b>Mening profilim</b>\n\n"
        "🆔 ID: <code>{user_id}</code>\n"
        "👤 Ism: <b>{full_name}</b>\n"
        "📞 Tel: <b>{phone_number}</b>\n"
        "📊 Status: {status_emoji} <b>{status_text}</b>\n"
        "⏳ Obuna tugash sanasi: <b>{expires_at_str}</b>\n\n"
        "📋 <b>Forma va tana parametrlari:</b>\n"
        "👤 Jins: <b>{gender}</b>\n"
        "📏 Bo'y: <b>{height_cm}</b>\n"
        "⚖️ Boshlang'ich vazn: <b>{initial_weight_kg}</b>\n"
        "⚖️ Hozirgi vazn: <b>{current_weight_kg}</b>\n"
        "🎯 Maqsad: <b>{goal}</b>\n\n"
        "🎁 <b>Balans va referal:</b>\n"
        "💰 Keshbek balansi: <b>{balance} UZS</b>\n"
        "👥 Taklif qilinganlar soni: <b>{invited_count} ta</b>\n"
        "🔗 Havola: <code>{ref_link}</code>"
    ),
    "ru": (
        "👤 <b>Мой профиль</b>\n\n"
        "🆔 ID: <code>{user_id}</code>\n"
        "👤 Имя: <b>{full_name}</b>\n"
        "📞 Тел: <b>{phone_number}</b>\n"
        "📊 Статус: {status_emoji} <b>{status_text}</b>\n"
        "⏳ Окончание подписки: <b>{expires_at_str}</b>\n\n"
        "📋 <b>Параметры фигуры:</b>\n"
        "👤 Пол: <b>{gender}</b>\n"
        "📏 Рост: <b>{height_cm}</b>\n"
        "⚖️ Стартовый вес: <b>{initial_weight_kg}</b>\n"
        "⚖️ Текущий вес: <b>{current_weight_kg}</b>\n"
        "🎯 Цель: <b>{goal}</b>\n\n"
        "🎁 <b>Баланс и рефералы:</b>\n"
        "💰 Баланс кешбэка: <b>{balance} UZS</b>\n"
        "👥 Приглашено друзей: <b>{invited_count} чел.</b>\n"
        "🔗 Ссылка: <code>{ref_link}</code>"
    )
}

EDIT_NAME_BTN = {"uz": "✏️ Ismni o'zgartirish", "ru": "✏️ Изменить имя"}
EDIT_PHONE_BTN = {"uz": "📞 Telefonni o'zgartirish", "ru": "📞 Изменить номер"}
EDIT_PHOTO_BTN = {"uz": "✏️ Rasmni yangilash", "ru": "✏️ Обновить фото"}
EDIT_PARAMS_BTN = {"uz": "✏️ Anketani tahrirlash", "ru": "✏️ Редактировать анкету"}
VIP_GROUP_BTN = {"uz": "👑 VIP Guruhga kirish", "ru": "👑 Войти в VIP-группу"}
VIP_GROUP_CARD = {
    "uz": (
        "👑 <b>VIP Guruh (6 oylik tarif)</b>\n\n"
        "Ushbu yopiq guruhda VIP ishtirokchilari bilan guruhli kechki ovqatlar "
        "(har oy 1 marta) anonslari e'lon qilinadi.\n\n"
        "🔑 <b>Shaxsiy bir martalik havolangiz:</b>\n{vip_link}\n\n"
        "⚠️ Bu havola faqat siz uchun. Uni boshqalarga bermang!"
    ),
    "ru": (
        "👑 <b>VIP-группа (тариф 6 месяцев)</b>\n\n"
        "В этой закрытой группе публикуются анонсы групповых ужинов с участниками VIP "
        "(1 раз в месяц).\n\n"
        "🔑 <b>Ваша персональная одноразовая ссылка:</b>\n{vip_link}\n\n"
        "⚠️ Ссылка только для вас. Не передавайте её другим!"
    )
}
VIP_GROUP_LINK_ERROR = {
    "uz": "⚠️ VIP guruh havolasini yaratishda xatolik yuz berdi. Iltimos, admin bilan bog'laning.",
    "ru": "⚠️ Не удалось создать ссылку на VIP-группу. Пожалуйста, свяжитесь с администратором."
}
NOT_SPECIFIED = {"uz": "Kiritilmagan", "ru": "Не указано"}
CHANGE_LANG_BTN = {"uz": "🌐 Tilni o'zgartirish (UZ/RU)", "ru": "🌐 Сменить язык (UZ/RU)"}

PROMPT_PHOTO_UPLOAD = {
    "uz": "📸 <b>Profil rasmiga yangi fotosurat yuboring:</b>",
    "ru": "📸 <b>Отправьте новую фотографию для профиля:</b>"
}
PHOTO_UPDATED_SUCCESS = {
    "uz": "✅ Profil rasmingiz muvaffaqiyatli saqlandi!",
    "ru": "✅ Фотография профиля успешно сохранена!"
}

PROMPT_NEW_NAME = {
    "uz": "✏️ Yangi Ism va Familiyangizni kiriting:",
    "ru": "✏️ Введите ваши новые Имя и Фамилию:"
}

PROMPT_NEW_PHONE = {
    "uz": "📞 Yangi telefon raqamingizni kiriting yoki «Raqamni yuborish» tugmasini bosing:",
    "ru": "📞 Введите ваш новый номер телефона или нажмите «Отправить номер»:"
}

NAME_UPDATED = {
    "uz": "✅ Ismingiz muvaffaqiyatli yangilandi!",
    "ru": "✅ Ваше имя успешно обновлено!"
}

PHONE_UPDATED = {
    "uz": "✅ Telefon raqamingiz muvaffaqiyatli yangilandi!",
    "ru": "✅ Ваш номер телефона успешно обновлен!"
}

STATUS_ACTIVE = {"uz": "FAOL", "ru": "АКТИВЕН"}
STATUS_EXPIRED = {"uz": "FAOL EMAS", "ru": "НЕАКТИВЕН"}

TARIFF_CARDS = {
    '1': {
        'uz': (
            "🥉 BAZAVIY — 500 000 so'm / 1 oy\n"
            "• Har oy 10 ta yangi mashg'ulot darsi\n"
            "• Guruhli qo'ng'iroq haftasiga 1 marta\n"
            '• Guruhli uchrashuv oyiga 1 marta\n'
            '• Ratsionni AI orqali hisoblash (foto orqali BJU)\n'
            "• AI yordamchi (mahsulot xaridi va ovqatlanish bo'yicha)"
        ),
        'ru': (
            '🥉 БАЗОВЫЙ — 500 000 сум / месяц\n'
            '• 10 новых тренировочных уроков каждый месяц\n'
            '• Групповой созвон 1 раз в неделю\n'
            '• Групповая встреча 1 раз в месяц\n'
            '• ИИ-расчёт БЖУ по фото еды\n'
            '• ИИ-помощник по закупу продуктов и питанию'
        ),
    },
    '3': {
        'uz': (
            "🥈 FITNES (ENG OMMABOP) — 1 200 000 so'm / 3 oy\n"
            "(Asl narxi: 1 500 000 so'm — 300 000 so'm tejang!)\n"
            '• Barcha «Bazaviy» imkoniyatlar 3 oy davomida\n'
            "• Har oy 10 ta yangi mashg'ulot darsi\n"
            "• Guruhli qo'ng'iroq haftasiga 1 marta\n"
            '• Guruhli uchrashuv oyiga 1 marta\n'
            '• Ratsionni AI orqali hisoblash va AI yordamchi'
        ),
        'ru': (
            '🥈 ФИТНЕС (ВЫГОДНЕЕ) — 1 200 000 сум / 3 месяца\n'
            '(Старая цена: 1 500 000 сум — экономия 300 000 сум!)\n'
            '• Все возможности тарифа «Базовый» на 3 месяца\n'
            '• 10 новых тренировочных уроков каждый месяц\n'
            '• Групповой созвон 1 раз в неделю\n'
            '• Групповая встреча 1 раз в месяц\n'
            '• ИИ-расчёт БЖУ и ИИ-помощник по питанию'
        ),
    },
    '6': {
        'uz': (
            "🥇 VIP — 2 300 000 so'm / 6 oy\n"
            "(Asl narxi: 3 000 000 so'm — 700 000 so'm tejang!)\n"
            '• «Fitnes» tarifidagi barcha imkoniyatlar 6 oy davomida\n'
            '• 👑 VIP BONUSLAR:\n'
            '— Har oy 1 marta guruhli kechki ovqat (VIP ishtirokchilari bilan)\n'
            '— Alohida yopiq VIP guruh'
        ),
        'ru': (
            '🥇 VIP — 2 300 000 сум / 6 месяцев\n'
            '(Старая цена: 3 000 000 сум — экономия 700 000 сум!)\n'
            '• Все возможности тарифа «Фитнес» на 6 месяцев\n'
            '• 👑 VIP-БОНУСЫ:\n'
            '— Групповой ужин 1 раз в месяц с участниками VIP\n'
            '— Отдельная VIP-группа для участников тарифа'
        ),
    },
}

ALL_TARIFFS_CARD = {
    'uz': (
        '🏋️\u200d♂️ O‘zingizga mos tarifni tanlang:\n'
        '\n'
        '🥉 1 oy — Bazaviy\n'
        '💰 500 000 so‘m/oy\n'
        '\n'
        '• Har oy 10 ta yangi mashg‘ulot\n'
        '• Haftasiga 1 marta guruhli qo‘ng‘iroq\n'
        '• Oyiga 1 marta guruhli uchrashuv\n'
        '• 🤖 Surat orqali BJU hisoblash\n'
        '• 🤖 Ovqatlanish va mahsulot xaridi bo‘yicha AI yordamchi\n'
        '\n'
        '⸻\n'
        '\n'
        '🥈 3 oy — Fitnes\n'
        '💰 1 200 000 so‘m/3 oy\n'
        '🔥 300 000 so‘m tejaysiz\n'
        '\n'
        '• «Bazaviy» tarifidagi barcha imkoniyatlar\n'
        '• 3 oy davomida kirish huquqi\n'
        '• Har oy 10 ta yangi mashg‘ulot\n'
        '• Guruhli qo‘ng‘iroqlar va uchrashuvlar\n'
        '• 🤖 Ovqatlanish bo‘yicha AI yordamchilar\n'
        '\n'
        '⸻\n'
        '\n'
        '🥇 6 oy — VIP\n'
        '💰 2 300 000 so‘m/6 oy\n'
        '🔥 700 000 so‘m tejaysiz\n'
        '\n'
        '• «Fitnes» tarifidagi barcha imkoniyatlar\n'
        '• 6 oy davomida kirish huquqi\n'
        '• 👑 Alohida VIP guruhi\n'
        '• 🍽️ Oyiga 1 marta yopiq guruhli kechki ovqat\n'
        '• VIP ishtirokchilari bilan muloqot va uchrashuvlar\n'
        '\n'
        '👇 Tarifni tanlang va o‘z natijangiz sari yo‘lni boshlang!'
    ),
    'ru': (
        '🏋️\u200d♂️ Выберите подходящий тариф:\n'
        '\n'
        '🥉 1 месяц — Базовый\n'
        '💰 500 000 сум/месяц\n'
        '\n'
        '• 10 новых тренировок каждый месяц\n'
        '• Групповой созвон 1 раз в неделю\n'
        '• Групповая встреча 1 раз в месяц\n'
        '• 🤖 ИИ-расчёт БЖУ по фото\n'
        '• 🤖 ИИ-помощник по питанию и закупу\n'
        '\n'
        '⸻\n'
        '\n'
        '🥈 3 месяца — Фитнес\n'
        '💰 1 200 000 сум/3 месяца\n'
        '🔥 Экономия 300 000 сум\n'
        '\n'
        '• Все возможности тарифа «Базовый»\n'
        '• Доступ на 3 месяца\n'
        '• 10 новых тренировок каждый месяц\n'
        '• Групповые созвоны и встречи\n'
        '• 🤖 ИИ-помощники по питанию\n'
        '\n'
        '⸻\n'
        '\n'
        '🥇 6 месяцев — VIP\n'
        '💰 2 300 000 сум/6 месяцев\n'
        '🔥 Экономия 700 000 сум\n'
        '\n'
        '• Все возможности тарифа «Фитнес»\n'
        '• Доступ на 6 месяцев\n'
        '• 👑 Отдельная VIP-группа\n'
        '• 🍽️ Закрытый групповой ужин 1 раз в месяц\n'
        '• Общение и встречи с участниками VIP\n'
        '\n'
        '👇 Выберите тариф и начните путь к своему результату!'
    ),
}

CASHBACK_ASK = {
    "uz": (
        "🎁 <b>Sizda {balance} UZS keshbek mavjud!</b>\n\n"
        "Tarif narxi: <b>{tariff_price} UZS</b>\n"
        "To'lov summasi: <b>{final_price} UZS</b>\n\n"
        "To'lovda keshbekdan foydalanasizmi?"
    ),
    "ru": (
        "🎁 <b>У вас есть {balance} UZS кешбэка!</b>\n\n"
        "Стоимость тарифа: <b>{tariff_price} UZS</b>\n"
        "Итого к оплате: <b>{final_price} UZS</b>\n\n"
        "Хотите использовать кешбэк при оплате?"
    )
}

CASHBACK_USE_BTN = {
    "uz": "✅ Ha, keshbekni ishlatish",
    "ru": "✅ Да, использовать кешбэк"
}

CASHBACK_FULL_BTN = {
    "uz": "❌ Yo'q, to'liq to'lash",
    "ru": "❌ Нет, оплатить полностью"
}

SHARE_REF_BTN = {
    "uz": "🔗 Havolani ulashish",
    "ru": "🔗 Поделиться ссылкой"
}

CASHBACK_NOTIFY_REFERRER = {
    "uz": "🎉 Siz taklif qilgan do'stingiz obuna bo'ldi! Balansingizga +30 000 UZS keshbek qo'shildi.",
    "ru": "🎉 Ваш приглашённый друг оформил подписку! На ваш баланс начислено +30 000 UZS кешбэка."
}

MENU_BUTTONS = {
    "training": {"uz": "🏋️ Mashg'ulotlar", "ru": "🏋️ Тренировки"},
    "profile": {"uz": "👤 Mening profilim", "ru": "👤 Мой профиль"},
    "fitness_hub": {"uz": "🧠 Sun'iy intellekt (AI)", "ru": "🧠 Искусственный интеллект (AI)"},
    "subscribe": {"uz": "🚀 Obuna bo'lish", "ru": "🚀 Оформить подписку"},
    "prolong": {"uz": "🔄 Obunani uzaytirish", "ru": "🔄 Продлить подписку"},
    "support": {"uz": "💬 Yordam / Qo'llab-quvvatlash", "ru": "💬 Служба поддержки"},
    "lang": {"uz": "🌐 Tilni o'zgartirish", "ru": "🌐 Сменить язык"},
    "referral": {"uz": "🤝 Do'stni taklif qilish", "ru": "🤝 Пригласить друга"},
    "food_calories": {"uz": "🍎 Foto bo'yicha kaloriya", "ru": "🍎 Калории по фото"},
    "meal_plan": {"uz": "📋 7 kunlik taomnoma & Bozorlik", "ru": "📋 7 kunlik рацион & Шопинг-лист"},
    "weight_log": {"uz": "⚖️ Vazn & Dinamika grafigi", "ru": "⚖️ Вес & График динамики"},
    "allowed_foods": {"uz": "🥗 Ruxsat / Taqiqlangan mahsulotlar", "ru": "🥗 Разрешённые / Запрещённые продукты"},
    "ai_coach": {"uz": "🤖 Cho'ntak nutritsiologi (AI)", "ru": "🤖 Карманный нутрициолог (ИИ)"}
}

REF_PROGRAM_TEXT = {
    "uz": (
        "🤝 <b>Do'stni taklif qilish va Keshbek dasturi</b>\n\n"
        "Sizning taklifnomangiz bo'yicha botga kelgan har bir do'stingiz birinchi obunasini rasmiylashtirganda, balansingizga <b>+30 000 UZS</b> keshbek avtomatik ravishda o'tkaziladi!\n\n"
        "📊 <b>Sizning ko'rsatkichlaringiz:</b>\n"
        "👥 Taklif qilingan do'stlar: <b>{invited_count} ta</b>\n"
        "💰 Mavjud keshbek balansi: <b>{balance:,} UZS</b>\n\n"
        "🔗 <b>Sizning shaxsiy referal havolangiz:</b>\n"
        "<code>{ref_link}</code>\n\n"
        "💡 <i>Ushbu havolani do'stlaringizga yuboring va keshbekingizni keyingi obunalarni to'lashda ishlating!</i>"
    ),
    "ru": (
        "🤝 <b>Реферальная программа и Кешбэк</b>\n\n"
        "За каждого друга, который зарегистрируется по вашей ссылке и оформит первую подписку, вы получите <b>+30 000 UZS</b> кешбэка на ваш баланс!\n\n"
        "📊 <b>Ваши показатели:</b>\n"
        "👥 Приглашено друзей: <b>{invited_count} чел.</b>\n"
        "💰 Баланс кешбэка: <b>{balance:,} UZS</b>\n\n"
        "🔗 <b>Ваша персональная реферальная ссылка:</b>\n"
        "<code>{ref_link}</code>\n\n"
        "💡 <i>Отправьте эту ссылку друзьям и используйте кешбэк при оплате подписки!</i>"
    )
}

FITNESS_HUB_TITLE = {
    "uz": "🧠 <b>Sun'iy intellekt (AI)</b>\n\nBarcha aqlli fitnes-vositalari va AI instrumentlar bir joyda. Kerakli bo'limni tanlang:",
    "ru": "🧠 <b>Искусственный интеллект (AI)</b>\n\nВсе умные фитнес-инструменты и AI-помощники в одном месте. Выберите нужный раздел:"
}

BACK_TO_HUB_BTN = {"uz": "◀️ Smart Hub'ga qaytish", "ru": "◀️ Вернуться в Smart Hub"}
BACK_TO_MAIN_BTN = {"uz": "◀️ Asosiy menyuga qaytish", "ru": "◀️ Вернуться в главное меню"}

MEAL_PLAN_PROMPT = {
    "uz": "📋 <b>7 kunlik shaxsiy taomnoma va Bozorlik ro'yxati</b>\n\nSun'iy intellekt sizning tana parametrlaringiz va maqsadingiz asosida taomnoma shakllantirmoqda. Iltimos kuting...",
    "ru": "📋 <b>Персональное 7-дневное меню и Шопинг-лист</b>\n\nИИ формирует ваш рацион и список покупок на основе ваших параметров и цели. Пожалуйста, подождите..."
}

MEAL_PLAN_REGENERATE_BTN = {"uz": "🔄 Taomnomani yangilash", "ru": "🔄 Обновить рацион"}

ALLOWED_FORBIDDEN_TEXT = {
    "uz": (
        "🥗 <b>Ruxsat berilgan va Taqiqlangan mahsulotlar ro'yxati</b>\n\n"
        "✅ <b>Tavsiya etiladi (Fayzli oqsillar, murakkab uglevodlar, to'g'ri yog'lar):</b>\n"
        "• 🥩 <b>Oqsil:</b> Tovuq ko'kragi, mol go'shti, kurka, baliq, tuxum, kam yog'li tvorog, grek yogurti.\n"
        "• 🍚 <b>Murakkab uglevodlar:</b> Suli (ovsyanka), grechka, jigarrang va oq guruch, bulgur, qattiq navli makaron.\n"
        "• 🥑 <b>To'g'ri yog'lar:</b> Zaytun yog'i, bodom, yong'oq, avokado, zig'ir va kunjut urug'lari.\n"
        "• 🥗 <b>Kletchatka:</b> Bodring, pomidor, karam, ismaloq, ko'katlar, yangi uzilgan meva va rezavorlar.\n\n"
        "❌ <b>Qat'iy tavsiya etilmaydi (Shakar, fastfud, trans-yog'lar):</b>\n"
        "• 🚫 <b>Shakar va shirinliklar:</b> Oq shakar, tortlar, pishiriqlar, shokoladli plitkalar, shirin pechenyelar.\n"
        "• 🚫 <b>Fastfud:</b> Gamburger, lavash, kartoshka fri, pirojki, chipslar, suxariklar.\n"
        "• 🚫 <b>Gazli va shirin ichimliklar:</b> Coca-Cola, Fanta, do'kon sharbatlari, energetiklar, spirtli ichimliklar.\n"
        "• 🚫 <b>Trans-yog'lar va soslar:</b> Margarin, mayonez, ketchup, do'kon soslari, kolbasa va sosiskalar.\n\n"
        "💡 <i>Tavsiya: Ovqatlanish ratsioningizni 80/20 qoidasi bo'yicha tuzing, toza suv ichishni unutmang!</i>"
    ),
    "ru": (
        "🥗 <b>Список разрешённых и Запрещённых продуктов</b>\n\n"
        "✅ <b>Рекомендуется (Качественные белки, сложные углеводы, правильные жиры):</b>\n"
        "• 🥩 <b>Белки:</b> Куриная грудка, говядина, индейка, рыба, яйца, нежирный творог, греческий йогурт.\n"
        "• 🍚 <b>Сложные углеводы:</b> Овсянка, гречка, бурый и белый рис, булгур, макароны из твёрдых сортов.\n"
        "• 🥑 <b>Правильные жиры:</b> Оливковое масло, миндаль, грецкие орехи, авокадо, семена льна и кунжута.\n"
        "• 🥗 <b>Клетчатка:</b> Огурцы, помидоры, капуста, шпинат, зелень, свежие фрукты и ягоды.\n\n"
        "❌ <b>Строго не рекомендуется (Сахар, фастфуд, транснасыщенные жиры):</b>\n"
        "• 🚫 <b>Сахар и сладости:</b> Белый сахар, торты, выпечка, конфеты, шоколадные батончики.\n"
        "• 🚫 <b>Фастфуд:</b> Гамбургеры, лаваш, картофель фри, пирожки, чипсы, сухарики.\n"
        "• 🚫 <b>Сладкие газированные напитки:</b> Coca-Cola, Fanta, пакетированные соки, энергетики, алкоголь.\n"
        "• 🚫 <b>Трансжиры и соусы:</b> Маргарин, майонез, кетчуп, покупные соусы, колбасы и сосиски.\n\n"
        "💡 <i>Совет: Стройте ваш рацион по правилу 80/20 и поддерживайте питьевой режим!</i>"
    )
}

WEIGHT_SUBMENU_TEXT = {
    "uz": "⚖️ <b>Vazn va Dinamika grafigi</b>\n\nJoriy vazningizni yozib boring yoki o'zgarishlar grafigini tomosha qiling:",
    "ru": "⚖️ <b>Вес и График динамики</b>\n\nЗапишите ваш текущий вес или посмотрите график изменений:"
}
WEIGHT_ADD_BTN = {"uz": "⚖️ Vaznni yozish", "ru": "⚖️ Записать вес"}
WEIGHT_CHART_BTN = {"uz": "📈 Grafig ko'rish", "ru": "📈 График динамики"}

INVITE_FRIEND_BTN = {
    "uz": "🎁 Do'stni taklif qilish (+30 000 UZS)",
    "ru": "🎁 Пригласить друга (+30 000 UZS)"
}

GUARD_ACCESS_DENIED = {
    "uz": "🔒 Bu funksiya faqat klubning faol a'zolari uchun mavjud. Foydalanish uchun obunangizni faollashtiring yoki uzaytiring! 🏋️‍♂️",
    "ru": "🔒 Эта функция доступна только активным участникам клуба. Оформите или продлите подписку для доступа! 🏋️‍♂️"
}

PROFILE_ASK_GOAL = {
    "uz": "🎯 <b>Asosiy maqsadingizni tanlang:</b>",
    "ru": "🎯 <b>Выберите вашу основную цель:</b>"
}

GOAL_OPTIONS = {
    "weight_loss": {"uz": "📉 Ozish", "ru": "📉 Похудение"},
    "keep_fit": {"uz": "🤸‍♀️ Qomatni saqlash", "ru": "🤸‍♀️ Поддержание формы"},
    "muscle_gain": {"uz": "🏋️‍♂️ Mushak massasi yig'ish", "ru": "🏋️‍♂️ Набор массы"}
}

PROFILE_ASK_WEIGHT = {
    "uz": "⚖️ <b>Joriy vazningizni kg da kiriting (masalan: 70):</b>",
    "ru": "⚖️ <b>Введите ваш текущий вес в кг (например: 70):</b>"
}

PROFILE_ASK_GENDER = {
    "uz": "👤 <b>Jinsingizni tanlang:</b>",
    "ru": "👤 <b>Выберите ваш пол:</b>"
}

GENDER_OPTIONS = {
    "M": {"uz": "👨 Erkak", "ru": "👨 Мужской"},
    "F": {"uz": "👩 Ayol", "ru": "👩 Женский"}
}

SKIP_BTN = {
    "uz": "⏭ O'tkazib yuborish",
    "ru": "⏭ Пропустить"
}

PROFILE_ASK_HEIGHT = {
    "uz": "📏 <b>Bo'yingizni sm da kiriting (masalan: 175) yoki [⏭ O'tkazib yuborish] tugmasini bosing:</b>",
    "ru": "📏 <b>Введите ваш рост в см (например: 175) или нажмите [⏭ Пропустить]:</b>"
}

PROFILE_ASK_BODY_PHOTO = {
    "uz": (
        "📸 <b>Qomat va tana tuzilishingizni tahlil qilish uchun rasm yuboring</b>\n\n"
        "❓ <b>Nima uchun foto kerak?</b>\n"
        "Sun'iy intellekt va murabbiy tana tuzilishingiz hamda muammoli zonalarni (yog' to'plangan joylar, mushak balansi) aniqroq tahlil qilib, siz uchun individual taomnoma va tavsiyalar tuzishi uchun.\n\n"
        "🔒 <b>Maxfiylik kafolati:</b>\n"
        "Fotosuratingiz 100% maxfiy qoladi va hech qayerga tarqatilmaydi! U faqat ma'lumotlar bazasida xavfsiz file_id ko'rinishida saqlanadi.\n\n"
        "📋 <b>Tavsiya etilgan rasm:</b>\n"
        "• Qomatingiz ko'rinadigan qulay sport kiyimida to'liq bo'y-bast rasm.\n"
        "• Yuzingizni yopishingiz mumkin (ixtiyoriy).\n\n"
        "<i>Rasmni yuboring yoki quyidagi [⏭ O'tkazib yuborish] tugmasini bosing:</i>"
    ),
    "ru": (
        "📸 <b>Отправьте фото вашей фигуры (для анализа формы тела)</b>\n\n"
        "❓ <b>Зачем нужно фото?</b>\n"
        "ИИ и тренер анализируют пропорции вашего тела и проблемные зоны для точного составления персонального рациона и программы.\n\n"
        "🔒 <b>Гарантия конфиденциальности:</b>\n"
        "Ваша фотография на 100% конфиденциальна и никуда не передаётся! Она сохраняется исключительно в виде зашифрованного file_id в базе данных.\n\n"
        "📋 <b>Рекомендации к фото:</b>\n"
        "• Фото в полный рост в спортивной одежде.\n"
        "• Лицо можно прикрыть (по желанию).\n\n"
        "<i>Отправьте фото или нажмите кнопку [⏭ Пропустить]:</i>"
    )
}

PROFILE_SAVED = {
    "uz": "✅ Anketa ma'lumotlaringiz saqlandi! Endi barcha imkoniyatlardan foydalanishingiz mumkin.",
    "ru": "✅ Данные анкеты сохранены! Теперь вы можете пользоваться всеми возможностями."
}

CALORIE_PROMPT = {
    "uz": "📸 <b>Kaloriyalarni hisoblash</b>\n\nIltimos, taomingiz fotosuratini yuboring:",
    "ru": "📸 <b>Подсчёт калорий по фото</b>\n\nПожалуйста, отправьте фотографию вашей еды:"
}

CALORIE_ANALYZING = {
    "uz": "🔄 <i>Sun'iy intellekt taomni tahlil qilmoqda, iltimos kuting...</i>",
    "ru": "🔄 <i>ИИ анализирует блюдо, пожалуйста, подождите...</i>"
}

CALORIE_CARD = {
    "uz": (
        "🍎 <b>Taom: {dish}</b> (~{weight_g} g)\n\n"
        "🔥 Kaloriya: <b>{calories} kkal</b>\n"
        "🥩 Oqsil: <b>{protein} g</b>\n"
        "🥑 Yog': <b>{fat} g</b>\n"
        "🍞 Uglevod: <b>{carbs} g</b>\n\n"
        "💡 <i>{tip}</i>\n\n"
        "📊 <b>Bugun jami to'plangan kaloriya:</b> <b>{today_calories} kkal</b>"
    ),
    "ru": (
        "🍎 <b>Блюдо: {dish}</b> (~{weight_g} г)\n\n"
        "🔥 Калории: <b>{calories} ккал</b>\n"
        "🥩 Белки: <b>{protein} г</b>\n"
        "🥑 Жиры: <b>{fat} г</b>\n"
        "🍞 Углеводы: <b>{carbs} г</b>\n\n"
        "💡 <i>{tip}</i>\n\n"
        "📊 <b>Всего калорий за сегодня:</b> <b>{today_calories} ккал</b>"
    )
}

WEIGHT_PROMPT = {
    "uz": "⚖️ <b>Vaznni yozib borish</b>\n\nJoriy vazningizni kiriting (masalan: <code>75.5</code>):",
    "ru": "⚖️ <b>Запись веса</b>\n\nВведите ваш текущий вес в кг (например: <code>75.5</code>):"
}

WEIGHT_INVALID = {
    "uz": "❌ Noto'g'ri format. Musbat son kiriting (masalan: 75.5):",
    "ru": "❌ Некорректный формат. Введите положительное число (например: 75.5):"
}

WEIGHT_SAVED = {
    "uz": "✅ Vazningiz muvaffaqiyatli saqlandi: <b>{weight} kg</b>!",
    "ru": "✅ Ваш вес успешно сохранён: <b>{weight} кг</b>!"
}

WEIGHT_NO_DATA = {
    "uz": "📈 Sizda hali vazn yozuvlari mavjud emas. Avval «⚖️ Vaznni yozib borish» tugmasi orqali vazningizni kiriting.",
    "ru": "📈 У вас пока нет записей веса. Сначала внесите вес через кнопку «⚖️ Записать вес»."
}

AI_NUTRITIONIST_WELCOME = {
    "uz": (
        "🤖 <b>«Cho'ntak nutritsiologi» (AI yordamchisi)</b>\n\n"
        "Mashg'ulotlar, PP-retseptlar, kaloriya defitsiti va kun tartibi bo'yicha savollaringizni berishingiz mumkin.\n\n"
        "Menyuga qaytish uchun <b>«◀️ AI rejimidan chiqish»</b> tugmasini bosing."
    ),
    "ru": (
        "🤖 <b>«Карманный нутрициолог» (ИИ-ассистент)</b>\n\n"
        "Задайте любой вопрос по тренировкам, ПП-рецептам, дефициту калорий или режиму дня.\n\n"
        "Для возврата в меню нажмите кнопку <b>«◀️ Выйти из режима ИИ»</b>."
    )
}

AI_EXIT_BTN = {
    "uz": "◀️ AI rejimidan chiqish",
    "ru": "◀️ Выйти из режима ИИ"
}

AI_EXIT_MSG = {
    "uz": "◀️ Siz AI rejimidan chiqdingiz va asosiy menyuga qaytdingiz.",
    "ru": "◀️ Вы вышли из режима ИИ и вернулись в главное меню."
}

REFERRAL_CARD_TEXT = {
    "uz": (
        "🎁 <b>Do'stlarni taklif qiling va keshbek oling!</b>\n\n"
        "🔗 Sizning shaxsiy referal havolangiz:\n"
        "<code>{ref_link}</code>\n\n"
        "💰 Har bir taklif qilingan do'stingiz birinchi obunasini to'laganda sizga <b>30 000 UZS</b> beriladi!"
    ),
    "ru": (
        "🎁 <b>Приглашайте друзей и получайте кешбэк!</b>\n\n"
        "🔗 Ваша персональная реферальная ссылка:\n"
        "<code>{ref_link}</code>\n\n"
        "💰 За каждого друга, оформившего первую подписку по вашей ссылке, вам начисляется <b>30 000 UZS</b>!"
    )
}

SUB_PROLONG = {"uz": "🔄 Obunani uzaytirish", "ru": "🔄 Продлить подписку"}
CHOOSE_TARIFF = {"uz": "O'zingizga mos tarifni tanlang:", "ru": "Выберите подходящий тариф:"}

REG_ASK_NAME = {"uz": "Obunani rasmiylashtirish uchun, iltimos, Ismingiz va Familiyangizni kiriting:", "ru": "Для оформления подписки, пожалуйста, введите ваши Имя и Фамилию:"}
REG_ASK_PHONE_KB = {"uz": "📱 Raqamni yuborish", "ru": "📱 Отправить номер"}
REG_ASK_PHONE = {"uz": "Aktivatsiya qilish uchun telefon raqamingizni yuboring:", "ru": "Для активации отправьте ваш номер телефона:"}
REG_SUCCESS = {"uz": "✅ Ma'lumotlaringiz muvaffaqiyatli saqlandi!", "ru": "✅ Ваши данные успешно сохранены!"}

PAY_TARIFF_INFO = {
    "uz": (
        "💳 <b>{months} oylik tarifi tanlandi</b>\n\n"
        "💰 To'lov miqdori: <b>{price} UZS</b>\n\n"
        "⏳ Obuna tugash sanasi: <b>{expires_at}</b>\n\n"
        "⚡️ <b>To'lov usullari:</b>\n\n"
        "Payme, Click, Uzum Bank yoki bank kartalari (Uzcard / Humo) orqali bir zumda to'lashingiz mumkin.\n\n"
        "To'lovni amalga oshirish uchun pastdagi «To'lov qilish» tugmasini bosing.\n\n"
        "To'lov tasdiqlanishi bilan bot sizga avtomatik ravishda yopiq fitnes-kanalga bir marta ishlatiladigan taklifnoma havolasini yuboradi!"
    ),
    "ru": (
        "💳 <b>Выбран тариф: {months} мес.</b>\n\n"
        "💰 Сумма к оплате: <b>{price} UZS</b>\n\n"
        "⏳ Дата окончания подписки: <b>{expires_at}</b>\n\n"
        "⚡️ <b>Способы оплаты:</b>\n\n"
        "Вы можете моментально оплатить через Payme, Click, Uzum Bank или банковские карты (Uzcard / Humo).\n\n"
        "Для оплаты нажмите кнопку «Оплатить» ниже.\n\n"
        "После подтверждения платежа бот автоматически отправит вам одноразовую ссылку-приглашение в закрытый фитнес-канал!"
    )
}

PAY_BTN = {"uz": "💳 To'lov qilish", "ru": "💳 Оплатить"}
BACK_BTN = {"uz": "◀️ Orqaga", "ru": "◀️ Назад"}

MANUAL_PAY_INFO = {
    "uz": (
        "⚠️ <b>Qo'lda to'lov qilish:</b>\n\n"
        "Iltimos, {price} UZS summani quyidagi kartaga o'tkazing:\n"
        "💳 <code>8600 0000 0000 0000</code>\n"
        "👤 Qabul qiluvchi: Ism F.\n\n"
        "To'lovni amalga oshirgach, <b>«To'lov qildim»</b> tugmasini bosing."
    ),
    "ru": (
        "⚠️ <b>Ручная оплата:</b>\n\n"
        "Пожалуйста, переведите сумму {price} UZS на следующую карту:\n"
        "💳 <code>8600 0000 0000 0000</code>\n"
        "👤 Получатель: Имя Ф.\n\n"
        "После совершения оплаты нажмите кнопку <b>«Я оплатил»</b>."
    )
}

PAY_PAID_BTN = {"uz": "✅ To'lov qildim", "ru": "✅ Я оплатил"}

PENDING_ADMIN = {
    "uz": "⏳ <b>Sizning arizangiz adminga yuborildi!</b>\n\nAdmin to'lovingizni tasdiqlashi bilan sizga kanalga kirish uchun maxsus havola yuboriladi.\nIltimos, kuting...",
    "ru": "⏳ <b>Ваша заявка отправлена администратору!</b>\n\nКак только администратор подтвердит платеж, вы получите специальную ссылку для входа в канал.\nПожалуйста, подождите..."
}

SUPPORT_PROMPT = {
    "uz": "✍️ Iltimos, muammongizni yoki savolingizni bitta xabarda batafsil yozib yuboring:",
    "ru": "✍️ Пожалуйста, опишите вашу проблему или вопрос подробно в одном сообщении:"
}
SUPPORT_TICKET_CREATED = {
    "uz": "✅ Sizning arizangiz qabul qilindi, administrator tez orada javob beradi.",
    "ru": "✅ Ваша заявка принята, администратор скоро ответит."
}
SUPPORT_ALREADY_OPEN = {
    "uz": "⏳ Sizda allaqachon ochiq ariza mavjud. Iltimos, administrator javobini kuting.",
    "ru": "⏳ У вас уже есть открытая заявка. Пожалуйста, ожидайте ответа администратора."
}
SUPPORT_CLOSED = {
    "uz": "✅ Sizning arizangiz administrator tomonidan yopildi. Yana savollar bo'lsa, /start buyrug'idan foydalaning.",
    "ru": "✅ Ваша заявка закрыта администратором. Если у вас остались вопросы, используйте команду /start."
}
SUPPORT_IN_SESSION_HINT = {
    "uz": "🟢 Siz hozir administrator bilan suhbatdasiz. Yozgan xabarlaringiz unga yetib boradi.",
    "ru": "🟢 Вы сейчас в диалоге с администратором. Ваши сообщения доставляются ему."
}

EXPIRED = {
    "uz": (
        "😔 <b>Obuna muddatingiz tugadi.</b>\n\n"
        "Siz yopiq fitnes-kanaldan vaqtincha chiqarildingiz.\n\n"
        "🤝 Formangizni yaxshilash va vazn tashlashga hech qachon kech emas!\n\n"
        "Istalgan vaqtda tarifni qayta tanlab, yopiq klubimizga va mashg'ulotlarga qaytishingiz mumkin.\n\n"
        "Qayta qo'shilish uchun /start buyrug'ini yuboring!"
    ),
    "ru": (
        "😔 <b>Срок вашей подписки истек.</b>\n\n"
        "Вы временно исключены из закрытого фитнес-канала.\n\n"
        "🤝 Никогда не поздно улучшить форму и сбросить вес!\n\n"
        "Вы можете в любое время снова выбрать тариф и вернуться к тренировкам в наш закрытый клуб.\n\n"
        "Для повторного подключения отправьте команду /start!"
    )
}

REMIND_3D = {
    "uz": (
        "⏰ <b>Yopiq fitnes-klubga obunangiz tugashiga 3 kun qoldi!</b>\n\n"
        "Sizning obunangiz {expiry} kuni yakuniga yetadi.\n\n"
        "Erishgan natijalaringizni yo'qotmaslik hamda mashg'ulotlar va taomnomani uzluksiz davom ettirish uchun obunangizni hoziroq uzaytiring! 🏋️‍♂️\n\n"
        "🔄 Hozir uzaytirsangiz, yangi muddat joriy obunangiz tugagan vaqtdan boshlab qo'shiladi."
    ),
    "ru": (
        "⏰ <b>Осталось 3 дня до конца подписки на закрытый фитнес-клуб!</b>\n\n"
        "Ваша подписка истекает {expiry}.\n\n"
        "Чтобы не потерять достигнутые результаты и продолжить тренировки без перерыва, продлите подписку прямо сейчас! 🏋️‍♂️\n\n"
        "🔄 Если вы продлите подписку сейчас, новый срок начнется с момента окончания текущего."
    )
}

REMIND_1D = {
    "uz": (
        "🔥 <b>Diqqat! Obunangiz 24 soatdan keyin tugaydi!</b>\n\n"
        "Ertaga {expiry} vaqti bilan obunangiz o'z nihoyasiga yetadi.\n\n"
        "Go'zal tana va natijalar sari tashlangan qadamingiz to'xtab qolmasin! Kanalga kirish uchun «Obunani uzaytirish» menyusidan foydalaning 👇"
    ),
    "ru": (
        "🔥 <b>Внимание! Ваша подписка истекает через 24 часа!</b>\n\n"
        "Завтра в {expiry} срок вашей подписки закончится.\n\n"
        "Не останавливайтесь на пути к красивому телу и отличным результатам! Продлите доступ прямо сейчас 👇"
    )
}

PAYMENT_FAILED = {
    "uz": "❌ To'lovingiz 24 soat ichida tasdiqlanmadi. Siz kanaldan chiqarildingiz.",
    "ru": "❌ Ваша оплата не была подтверждена в течение 24 часов. Вы исключены из канала."
}

PAYMENT_SUCCESS = {
    "uz": (
        "🎉 <b>Tabriklaymiz! To'lov muvaffaqiyatli amalga oshirildi.</b>\n\n"
        "Siz yangi, sog'lom va ko'rkam tanangiz sari birinchi muhim qadamni tashladingiz! 💪\n\n"
        "🔑 <b>Sizning shaxsiy taklifnoma havolangiz:</b>\n\n"
        "{invite_link}\n\n"
        "⚠️ Diqqat: Bu havola bir martalik bo'lib, faqat siz uchun yaratilgan. Uni boshqalarga uzatmang!\n\n"
        "📅 Obuna tugash sanasi: {expires_at}"
    ),
    "ru": (
        "🎉 <b>Поздравляем! Оплата успешно завершена.</b>\n\n"
        "Вы сделали первый важный шаг к новому, здоровому и красивому телу! 💪\n\n"
        "🔑 <b>Ваша персональная ссылка-приглашение:</b>\n\n"
        "{invite_link}\n\n"
        "⚠️ Внимание: Эта ссылка одноразовая и создана только для вас. Не передавайте её другим!\n\n"
        "📅 Дата окончания подписки: {expires_at}"
    )
}

PAYMENT_FAILED_NOTIFY = {
    "uz": "❌ <b>Sizning to'lovingiz rad etildi.</b> Iltimos, ma'lumotlarni tekshirib qaytadan urinib ko'ring yoki admin bilan bog'laning.",
    "ru": "❌ <b>Ваш платеж был отклонен.</b> Пожалуйста, проверьте данные и попробуйте снова, или свяжитесь с администратором."
}

PAYMENT_SUCCESS_ERROR = {
    "uz": "✅ To'lov tasdiqlandi, ammo kanal havolasini yaratishda xatolik yuz berdi. Iltimos, admin bilan bog'laning.",
    "ru": "✅ Оплата подтверждена, но произошла ошибка при создании ссылки на канал. Пожалуйста, свяжитесь с администратором."
}

PAYMENT_SUCCESS_VIP = {
    "uz": (
        "🎉 <b>Tabriklaymiz! VIP (6 oylik) to'lov muvaffaqiyatli amalga oshirildi.</b>\n\n"
        "Siz eng yaxshi natijalar sari VIP yo'lni tanladingiz! 💪\n\n"
        "🔑 <b>1. Asosiy yopiq kanal havolasi:</b>\n{invite_link}\n\n"
        "👑 <b>2. Yopiq VIP guruh havolasi:</b>\n{vip_link}\n\n"
        "VIP guruhda VIP ishtirokchilari bilan guruhli kechki ovqatlar "
        "(har oy 1 marta) anonslari e'lon qilinadi.\n\n"
        "⚠️ Ikkala havola ham bir martalik va faqat siz uchun. Ularni boshqalarga bermang!\n\n"
        "📅 Obuna tugash sanasi: {expires_at}"
    ),
    "ru": (
        "🎉 <b>Поздравляем! VIP-оплата (6 месяцев) успешно завершена.</b>\n\n"
        "Вы выбрали VIP-путь к лучшим результатам! 💪\n\n"
        "🔑 <b>1. Ссылка на основной закрытый канал:</b>\n{invite_link}\n\n"
        "👑 <b>2. Ссылка на закрытую VIP-группу:</b>\n{vip_link}\n\n"
        "В VIP-группе публикуются анонсы групповых ужинов с участниками VIP "
        "(1 раз в месяц).\n\n"
        "⚠️ Обе ссылки одноразовые и только для вас. Не передавайте их другим!\n\n"
        "📅 Дата окончания подписки: {expires_at}"
    )
}

VIP_EXPIRED = {
    "uz": (
        "😔 <b>Sizning VIP (6 oylik) obunangiz yakuniga yetdi.</b>\n\n"
        "Siz yopiq VIP guruhdan chiqarildingiz. Endi guruhli kechki ovqatlar "
        "anonslarini ko'ra olmaysiz.\n\n"
        "🤝 VIP darajaga qaytish va guruhli kechki ovqatlarda qatnashish uchun "
        "obunangizni hoziroq uzaytiring! 👇"
    ),
    "ru": (
        "😔 <b>Ваша VIP-подписка (6 месяцев) завершилась.</b>\n\n"
        "Вы исключены из закрытой VIP-группы и больше не будете видеть анонсы "
        "групповых ужинов с участниками VIP.\n\n"
        "🤝 Чтобы вернуть VIP-уровень и участвовать в закрытых встречах, "
        "продлите подписку прямо сейчас! 👇"
    )
}


CLICK_PAY_BTN = {
    "uz": "💳 Click orqali to'lash",
    "ru": "💳 Оплатить через Click",
}

CLICK_OPEN_BTN = {
    "uz": "🔗 To'lov sahifasini ochish",
    "ru": "🔗 Открыть страницу оплаты",
}

CLICK_PAY_INFO = {
    "uz": (
        "💳 <b>Click orqali to'lov</b>\n\n"
        "Buyurtma raqami: <code>{order_id}</code>\n"
        "To'lov summasi: <b>{price} UZS</b>\n\n"
        "Quyidagi tugma orqali to'lovni yakunlang. To'lov tasdiqlangandan so'ng "
        "kanalga havola avtomatik yuboriladi."
    ),
    "ru": (
        "💳 <b>Оплата через Click</b>\n\n"
        "Номер заказа: <code>{order_id}</code>\n"
        "Сумма к оплате: <b>{price} UZS</b>\n\n"
        "Завершите оплату по кнопке ниже. После подтверждения ссылка на канал "
        "придёт автоматически."
    ),
}


PAYME_PAY_BTN = {
    "uz": "💳 Payme orqali to'lash",
    "ru": "💳 Оплатить через Payme",
}

PAYME_OPEN_BTN = {
    "uz": "🔗 Payme'da to'lash",
    "ru": "🔗 Перейти к оплате Payme",
}

PAYME_PAY_INFO = {
    "uz": (
        "💳 <b>Payme orqali to'lov</b>\n\n"
        "Buyurtma raqami: <code>{order_id}</code>\n"
        "To'lov summasi: <b>{price} UZS</b>\n\n"
        "Quyidagi tugma orqali to'lovni yakunlang. To'lov tasdiqlangandan so'ng "
        "kanalga havola avtomatik yuboriladi."
    ),
    "ru": (
        "💳 <b>Оплата через Payme</b>\n\n"
        "Номер заказа: <code>{order_id}</code>\n"
        "Сумма к оплате: <b>{price} UZS</b>\n\n"
        "Завершите оплату по кнопке ниже. После подтверждения ссылка на канал "
        "придёт автоматически."
    ),
}


# Payme checkout is wired up but not yet switched on for payers: the button
# stays visible with a "soon" mark and a tap explains where to pay meanwhile.
PAYME_SOON_SUFFIX = {"uz": "(Tez kunda)", "ru": "(Скоро)"}

PAYME_SOON_ALERT = {
    "uz": (
        "⏳ Tez orada...\n\n"
        "Payme orqali to'lov tizimi tez kunlarda ishga tushiriladi. "
        "Hozircha Click orqali to'lashingiz mumkin."
    ),
    "ru": (
        "⏳ Скоро...\n\n"
        "Оплата через Payme заработает в ближайшие дни. "
        "Пока вы можете оплатить через Click."
    ),
}

# Alerts shown when a checkout button is tapped on a message that can no longer
# mint a payable order (stale, cancelled, paid, or covered by cashback).
PAYMENT_STALE_ALERT = {
    "uz": "To'lov muddati eskirgan. Iltimos, tarifni qaytadan tanlang.",
    "ru": "Платёж устарел. Откройте тариф заново.",
}
PAYMENT_ALREADY_PAID_ALERT = {
    "uz": "Bu buyurtma allaqachon to'langan.",
    "ru": "Этот заказ уже оплачен.",
}
PAYMENT_CANCELLED_ALERT = {
    "uz": "To'lov bekor qilingan. Iltimos, tarifni qaytadan tanlang.",
    "ru": "Платёж отменён. Откройте тариф заново.",
}
PAYMENT_COVERED_BY_CASHBACK_ALERT = {
    "uz": "Bu tarif keshbek bilan to'liq qoplanadi. Iltimos, tarifni qaytadan tanlang.",
    "ru": "Этот тариф покрыт кешбэком. Откройте тариф заново.",
}
CASHBACK_INSUFFICIENT_OR_STALE_ALERT = {
    "uz": "Keshbek yetarli emas yoki to'lov muddati eskirgan. Iltimos, tarifni qaytadan tanlang.",
    "ru": "Недостаточно кешбэка или платёж устарел. Откройте тариф заново.",
}
PAYMENT_ALREADY_PROCESSED_ALERT = {
    "uz": "Bu to'lov allaqachon qayta ishlangan.",
    "ru": "Этот платёж уже обработан.",
}
SUBSCRIPTION_ACTIVATED_ALERT = {
    "uz": "Obuna faollashtirildi. Havola avtomatik yuboriladi.",
    "ru": "Подписка активирована. Ссылка будет отправлена автоматически.",
}
CLICK_UNAVAILABLE_ALERT = {
    "uz": "Click vaqtincha ishlamayapti. Boshqa to'lov usulini tanlang.",
    "ru": "Click временно недоступен. Выберите другой способ оплаты.",
}
PAYME_UNAVAILABLE_ALERT = {
    "uz": "Payme vaqtincha ishlamayapti. Boshqa to'lov usulini tanlang.",
    "ru": "Payme временно недоступен. Выберите другой способ оплаты.",
}

# Replaces the keyboard of a stale checkout message with a single way forward.
OPEN_TARIFFS_AGAIN_BTN = {
    "uz": "🔄 Tariflarni qaytadan ochish",
    "ru": "🔄 Открыть тарифы заново",
}

SUPPORT_CANCELLED = {
    "uz": "❌ Murojaat bekor qilindi.",
    "ru": "❌ Обращение отменено.",
}

CLICK_CARD_INSTRUCTION = {
    'uz': (
        "💡 Click ilovangiz bo'lmasa ham to'lashingiz mumkin!\n\n"
        "Havolaga o'ting va 'Boshqa usul / Karta orqali to'lash' bo'limini tanlab, "
        "istalgan Uzcard yoki Humo kartangiz ma'lumotlarini kiritib to'lovni amalga oshiring."
    ),
    'ru': (
        "💡 Можно оплатить даже без приложения Click!\n\n"
        "Откройте ссылку, выберите 'Boshqa usul / Karta orqali to‘lash' "
        "и оплатите банковской картой Uzcard или Humo."
    ),
}
CLICK_VIDEO_INSTRUCTION = {
    'uz': "Quyidagi qisqa video-yo'riqnomada bu batafsil ko'rsatilgan 👇",
    'ru': "В короткой видеоинструкции показано, как это сделать 👇",
}
CLICK_CHECKOUT_OPEN = {
    'uz': "🔗 To'lov sahifasini ochish",
    'ru': '🔗 Открыть страницу оплаты',
}
