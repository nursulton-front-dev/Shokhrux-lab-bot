WELCOME_TEXT = {
    "uz": (
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
    ),
    "ru": (
        "🌟 <b>Добро пожаловать на путь к идеальной фигуре и здоровой жизни!</b>\n\n"
        "Вы получили приглашение не просто в канал, а в закрытый фитнес-клуб, который поможет вам достичь реальных результатов!\n\n"
        "Здесь вы получите не сухие и бесполезные советы из интернета, а четко работающую систему:\n\n"
        "🏋️‍♂️ <b>Что вас ждет в нашем закрытом канале?</b>\n\n"
        "• Эффективные программы тренировок для похудения и набора мышечной массы\n\n"
        "• Индивидуальное и вкусное меню (ПП-рецепты) для избавления от лишнего веса\n\n"
        "• Секреты ускорения обмена веществ и сохранения результата\n\n"
        "• Сильная мотивация и сообщество, которые не дадут вам остановиться\n\n"
        "🔥 Пришло время избавиться от лишнего веса и открыть лучшую версию себя!\n\n"
        "Выберите подходящий тариф и присоединяйтесь к нам прямо сейчас 👇"
    )
}

PROFILE_TEXT = {
    "uz": "👤 <b>Sizning profilingiz</b>\n\n🆔 ID: <code>{user_id}</code>\n\n📊 Status: {status_emoji} {status_text}\n\n⏳ Obuna tugash sanasi: {expires_at_str}\n\n💡 Obunangiz muddatini istalgan vaqtda uzaytirishingiz mumkin.",
    "ru": "👤 <b>Ваш профиль</b>\n\n🆔 ID: <code>{user_id}</code>\n\n📊 Статус: {status_emoji} {status_text}\n\n⏳ Дата окончания подписки: {expires_at_str}\n\n💡 Вы можете продлить подписку в любое время."
}

STATUS_ACTIVE = {"uz": "FAOL", "ru": "АКТИВЕН"}
STATUS_EXPIRED = {"uz": "MUDDATI TUGAGAN (yoki yo'q)", "ru": "ИСТЕКЛА (или нет)"}

MENU_BUTTONS = {
    "profile": {"uz": "👤 Mening profilim", "ru": "👤 Мой профиль"},
    "subscribe": {"uz": "🚀 Obuna bo'lish", "ru": "🚀 Оформить подписку"},
    "support": {"uz": "💬 Yordam", "ru": "💬 Поддержка"},
    "lang": {"uz": "🌐 Tilni o'zgartirish", "ru": "🌐 Сменить язык"}
}

SUB_PROLONG = {"uz": "🚀 Obunani uzaytirish / Xarid", "ru": "🚀 Продлить подписку / Купить"}
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

SUPPORT_TEXT = {
    "uz": "Savollaringiz bo'lsa, yordamchi administrator bilan bog'laning: @{username}",
    "ru": "Если у вас есть вопросы, свяжитесь с администратором поддержки: @{username}"
}
SUPPORT_NO_UNAME = {
    "uz": "Qo'llab-quvvatlash markazi bilan bog'lanish uchun adminimizga yozing.",
    "ru": "Для связи со службой поддержки напишите нашему администратору."
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
