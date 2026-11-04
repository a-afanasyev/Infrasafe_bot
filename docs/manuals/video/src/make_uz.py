"""rec.mjs → rec_uz.mjs и chat-player.html → chat-player-uz.html заменой строк (каждая обязана найтись)."""
PP = '/Users/andreyafanasyev/.claude/jobs/0653a80b/tmp/pp/'


def convert(src, dst, pairs):
    s = open(PP + src).read()
    for old, new in pairs:
        assert old in s, f'{src}: not found: {old[:60]}'
        s = s.replace(old, new)
    open(PP + dst, 'w').write(s)
    print('ok', dst)


# Реплики бота — дословно uk_management_bot/config/locales/uz.json.
BOT = [
    ("'👋 Добро пожаловать! Кто вы?\\n\\nЖитель — если вы живёте в доме.\\nСотрудник — если менеджер выдал вам код приглашения.'",
     "\"👋 Xush kelibsiz! Siz kimsiz?\\n\\nRezident — agar shu uyda yashasangiz.\\nXodim — agar menejer sizga taklif kodini bergan bo'lsa.\""),
    ("'👋 Добро пожаловать в систему!\\nСистема предназначена для жителей ЖК Olmazor Business City.\\nПри регистрации обязательно предоставьте свой номер телефона и документ, подтверждающий право собственности, или договор аренды.\\nС уважением, УК'",
     "\"👋 Tizimga xush kelibsiz!\\nTizim Olmazor Business City turar-joy majmuasi aholisi uchun mo'ljallangan.\\nRo'yxatdan o'tishda telefon raqamingizni va mulk huquqini tasdiqlovchi hujjatni yoki ijara shartnomasini taqdim etish majburiy.\\nHurmat bilan, Boshqaruv kompaniyasi\""),
    ("'✅ Телефон +998900000004 успешно сохранен!'", "'✅ Telefon +998900000004 saqlandi!'"),
    ("'📝 Заполните форму регистрации жителя — нажмите кнопку ниже:'",
     "\"📝 Turar joy egasi ro'yxatdan o'tish formasini to'ldiring — quyidagi tugmani bosing:\""),
    ("'📄 Обязательно приложите документ на квартиру: свидетельство о праве собственности (кадастровую выписку) или договор аренды. Документы временно хранятся в зашифрованном виде только на время проверки. После её завершения доступ к ним удаляется.'",
     "\"📄 Kvartira hujjatini albatta ilova qiling: mulk huquqi guvohnomasi (kadastr ko'chirmasi) yoki ijara shartnomasi. Hujjatlar faqat tekshiruv vaqtida shifrlangan holda vaqtincha saqlanadi. Tekshiruv tugagach, ularga kirish o'chiriladi.\""),
    ("'📄 Загрузка документов'", "'📄 Hujjatlar yuklanmoqda'"),
    ("'📤 Загрузите файл документа:\\n\\nТип документа: Право собственности'", "'📤 Hujjat faylini yuklash:\\n\\nHujjat turi: Mulk huquqi'"),
    ("'✅ Документ успешно сохранен!\\n\\nТип: Право собственности\\nФайл: photo.jpg'", "'✅ Hujjat muvaffaqiyatli saqlandi!\\n\\nTuri: Mulk huquqi\\nFayl: photo.jpg'"),
    ("'🎉 Профиль успешно заполнен!\\n\\n📊 Сводка загруженных документов:\\n📄 Всего документов: 1\\n- Право собственности: 1\\n\\n⏳ Ваша заявка отправлена на рассмотрение администратору. Ожидайте одобрения.'",
     "\"🎉 Ro'yxatdan o'tish tugallandi! Sizning ma'lumotlaringiz:\\n\\n📊 Yuklangan hujjatlarning qisqacha mazmuni:\\n📄 Jami hujjatlar: 1\\n- Mulk huquqi: 1\\n\\n⏳ Arizangiz moderatsiyaga yuborildi. Administrator tasdiqlashidan keyin arizalar yaratishingiz mumkin.\""),
    ("'✅ Ваша заявка одобрена! Нажмите кнопку ниже для перезапуска бота.'", "'✅ Arizangiz tasdiqlandi! Botni qayta ishga tushirish uchun quyidagi tugmani bosing.'"),
    ("'🔄 Бот был перезапущен. Выберите действие:'", "'🔄 Bot qayta ishga tushirildi. Amalni tanlang:'"),
    ("[['🏠 Право собственности', '📋 Договор аренды'], ['📄 Паспорт', '📄 Другие документы'], ['✅ Завершить онбординг']]",
     "[['🏠 Mulk huquqi', '📋 Ijara shartnomasi'], ['📄 Pasport', '📄 Boshqa hujjatlar'], [\"✅ Ro'yxatdan o'tishni yakunlash\"]]"),
    ("[['📝 Создать заявку', '📋 Мои заявки'], ['✅ Ожидают приёмки', '🚗 Контроль доступа'], ['👤 Профиль', 'ℹ️ Помощь'], ['📝 Обратная связь']]",
     "[['📝 Ariza yaratish', '📋 Mening arizalarim'], ['✅ Qabul qilish kutilmoqda', '🚗 Kirish nazorati'], ['👤 Profil', 'ℹ️ Yordam'], ['📝 Qayta aloqa']]"),
    ("['🏠 Я житель', '🧰 Я сотрудник (по приглашению)']", "['🏠 Men rezidentman', \"🧰 Men xodimman (taklif bo'yicha)\"]"),
    ("[['📱 Поделиться контактом'], ['📝 Регистрация (форма)']]", "[['📱 Kontaktni ulashish'], [\"📝 Ro'yxatdan o'tish (forma)\"]]"),
    ("[['🏠 Выбрать квартиру'], ['📝 Регистрация (форма)']]", "[['🏠 Kvartira tanlash'], [\"📝 Ro'yxatdan o'tish (forma)\"]]"),
    ("['🔗 Открыть форму']", "['🔗 Formani ochish']"),
    ("['📤 Загрузить документы']", "['📤 Hujjatlarni yuklash']"),
    ("['🔄 Перезапустить бота']", "['🔄 Botni qayta ishga tushirish']"),
    ("[['📄 Добавить еще документы', '✅ Завершить онбординг']]", "[[\"📄 Yana hujjatlar qo'shish\", \"✅ Ro'yxatdan o'tishni yakunlash\"]]"),
    ("chat('me', '📝 Регистрация (форма)', '09:32')", "chat('me', \"📝 Ro'yxatdan o'tish (forma)\", '09:32')"),
    ("chat('me', '🏠 Право собственности', '09:35')", "chat('me', '🏠 Mulk huquqi', '09:35')"),
    ("chat('me', '✅ Завершить онбординг', '09:36')", "chat('me', \"✅ Ro'yxatdan o'tishni yakunlash\", '09:36')"),
    ("'Поделиться номером телефона?', 'Бот получит ваш номер телефона.', ['ОТМЕНА', 'OK']",
     "'Telefon raqamini ulashasizmi?', 'Bot telefon raqamingizni oladi.', ['BEKOR QILISH', 'OK']"),
    ("chat('photo', '📷 фото документа', '09:35')", "chat('photo', '📷 hujjat rasmi', '09:35')"),
    ("chat('note', 'Бот удалил фото из чата')", "chat('note', \"Bot rasmni chatdan o'chirdi\")"),
    ("chat('note', 'Позже — после проверки')", "chat('note', \"Keyinroq — tekshiruvdan so'ng\")"),
]

# Цели нажатий — подписи кнопок на узбекском (бот и TWA).
TAPS = [
    ("tap('Я житель'", "tap('Men rezidentman'"),
    ("tap('Поделиться контактом'", "tap('Kontaktni ulashish'"),
    ("tap('Регистрация (форма)'", "tap(\"Ro'yxatdan o'tish (forma)\""),
    ("tap('Открыть форму'", "tap('Formani ochish'"),
    ("tap('Отправить заявку'", "tap('Arizani yuborish'"),
    ("tap('Загрузить документы'", "tap('Hujjatlarni yuklash'"),
    ("tap('🏠 Право собственности'", "tap('🏠 Mulk huquqi'"),
    ("tap('Завершить онбординг'", "tap(\"Ro'yxatdan o'tishni yakunlash\""),
    ("tap('Перезапустить бота'", "tap('Botni qayta ishga tushirish'"),
    ("tap('Приложение'", "tap('Ilova'"),
    ("tap('Создать'", "tap('Yaratish'"),
    ("tap('Сантехника'", "tap('Santexnika'"),
    ("tapButton('Далее'", "tapButton('Keyingisi'"),
    ("tap('Средняя'", "tap(\"O'rta\""),
    ("tapButton('Отправить заявку'", "tapButton('Ariza yuborish'"),
    ("tap('Засор в ванной'", "tap('Vannada tiqilib'"),
    (".type('Засор в ванной, вода уходит медленно.'", ".type('Vannada tiqilib qoldi, suv sekin ketyapti.'"),
]

CAPS = [
    ("'Регистрация занимает около минуты'", "\"Ro'yxatdan o'tish taxminan bir daqiqa oladi\""),
    ("'Отправьте боту /start и нажмите «Я житель»'", "'Botga /start yuboring va «Men rezidentman» tugmasini bosing'"),
    ("'Нажмите «Поделиться контактом» и подтвердите. Без телефона регистрация невозможна'",
     "\"«Kontaktni ulashish» tugmasini bosing va tasdiqlang. Telefonsiz ro'yxatdan o'tib bo'lmaydi\""),
    ("'Затем «Регистрация (форма)» → «Открыть форму»'", "\"So'ng «Ro'yxatdan o'tish (forma)» → «Formani ochish»\""),
    ("'Выберите двор, дом и квартиру'", "'Hovli, uy va kvartirani tanlang'"),
    ("'Проверьте данные и нажмите «Отправить заявку»'", "\"Ma'lumotlarni tekshiring va «Arizani yuborish» tugmasini bosing\""),
    ("'Вернитесь в чат и нажмите «Загрузить документы»'", "'Chatga qayting va «Hujjatlarni yuklash» tugmasini bosing'"),
    ("'Выберите «Право собственности» или «Договор аренды» и отправьте фото документа'",
     "'«Mulk huquqi» yoki «Ijara shartnomasi»ni tanlang va hujjat rasmini yuboring'"),
    ("'Нажмите «Завершить онбординг» и дождитесь проверки'", "\"«Ro'yxatdan o'tishni yakunlash» tugmasini bosing va tekshiruvni kuting\""),
    ("'После одобрения нажмите «Перезапустить бота» — готово!'", "'Tasdiqlangach, «Botni qayta ishga tushirish» tugmasini bosing — tayyor!'"),
    ("'Подать заявку — меньше минуты'", "'Ariza berish bir daqiqadan kam vaqt oladi'"),
    ("'Откройте приложение кнопкой «Приложение»'", "'Kiritish maydoni yonidagi «Ilova» tugmasi bilan ilovani oching'"),
    ("'Вкладка «Создать» → выберите, что случилось'", "\"«Yaratish» bo'limi → nima bo'lganini tanlang\""),
    ("'Выберите адрес: квартира, дом или двор'", "'Manzilni tanlang: kvartira, uy yoki hovli'"),
    ("'Опишите проблему'", "'Muammoni tasvirlab bering'"),
    ("'Фото — по желанию, до 5 штук'", "'Rasm — ixtiyoriy, 5 tagacha'"),
    ("'Выберите срочность. «Критическая» — только при аварии'", "\"Shoshilinchlikni tanlang. «Kritik» — faqat avariya bo'lganda\""),
    ("'Проверьте и нажмите «Отправить заявку»'", "'Tekshiring va «Ariza yuborish» tugmasini bosing'"),
    ("'Заявка создана. Статус видно на вкладке «Заявки», бот сообщит о каждом изменении'",
     "\"Ariza yaratildi. Holatini «Arizalar» bo'limida ko'rasiz, bot har bir o'zgarish haqida xabar beradi\""),
    ("'При аварии — сразу звоните диспетчеру'", "\"Avariya bo'lsa — darhol dispetcherga qo'ng'iroq qiling\""),
    # Титры.
    ("card('Инструкция для жителей', 'Регистрация', 'Понадобятся номер телефона\\nи документ на квартиру.')",
     "card(\"Aholi uchun yo'riqnoma\", \"Ro'yxatdan o'tish\", \"Telefon raqami va kvartira\\nhujjati kerak bo'ladi.\")"),
    ("card('Инструкция для жителей', 'Как подать заявку', 'Сантехника, электрика, лифт, уборка —\\nвсё через мини-приложение в Telegram.')",
     "card(\"Aholi uchun yo'riqnoma\", 'Ariza qanday beriladi', 'Santexnika, elektrika, lift, tozalash —\\nhammasi Telegramdagi mini-ilova orqali.')"),
    ("card('Готово', 'Спасибо!', 'Срочные проблемы — сразу звоните\\nдиспетчеру управляющей компании.')",
     "card('Tayyor', 'Rahmat!', \"Shoshilinch muammolarda darhol boshqaruv\\nkompaniyasi dispetcheriga qo'ng'iroq qiling.\")"),
]

ENV = [
    ("args: ['--lang=ru-RU', '--allow-file-access-from-files']", "args: ['--lang=uz-UZ', '--allow-file-access-from-files']"),
    ("await page.evaluateOnNewDocument(() => {\n  window.__tap",
     "await page.evaluateOnNewDocument(() => { try { localStorage.setItem('i18nextLng', 'uz') } catch (e) {} })\nawait page.evaluateOnNewDocument(() => {\n  window.__tap"),
    ("'/chat-player.html'", "'/chat-player-uz.html'"),
    ("{ id: 'a1', type: 'info', title: 'Отключение горячей воды', body: '5 ноября с 10:00 до 16:00 в домах ул. Садовая, 12 и 14 — плановые работы.' }",
     "{ id: 'a1', type: 'info', title: \"Issiq suv o'chiriladi\", body: \"5-noyabr kuni 10:00 dan 16:00 gacha Sadovaya ko'chasi, 12 va 14-uylarda rejali ishlar.\" }"),
    ("{ id: 'contacts', type: 'contact', title: 'Контакты', body: 'Диспетчерская: +998 71 000-00-00\\nАварийная служба: круглосуточно' }",
     "{ id: 'contacts', type: 'contact', title: 'Kontaktlar', body: 'Dispetcherlik: +998 71 000-00-00\\nAvariya xizmati: kecha-kunduz' }"),
    ("working_hours: 'Пн–Пт: 08:00–20:00\\nСб: 09:00–17:00\\nВс: выходной'", "working_hours: 'Du–Ju: 08:00–20:00\\nSha: 09:00–17:00\\nYak: dam olish kuni'"),
    ("J + '/captions.json'", "J + '/captions_uz.json'"),
]

convert('rec.mjs', 'rec_uz.mjs', BOT + TAPS + CAPS + ENV)
convert('chat-player.html', 'chat-player-uz.html', [
    ('<b>Бот управляющей компании</b>', '<b>Boshqaruv kompaniyasi boti</b>'),
    ('<div class="ph">Сообщение</div>', '<div class="ph">Xabar</div>'),
    ('☰ Приложение', '☰ Ilova'),
    ('class="av">УК', 'class="av">BK'),
    ('<span>бот</span>', '<span>bot</span>'),
])
