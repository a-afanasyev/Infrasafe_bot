// Запись скринкаста «Регистрация и заявки для жителя»: один непрерывный webm +
// captions.json (таймкоды субтитров от старта записи).
import puppeteer from 'puppeteer-core'
import fs from 'fs'

const J = '/Users/andreyafanasyev/.claude/jobs/0653a80b/tmp'
const PP = J + '/pp'
const CH = '/Users/andreyafanasyev/.cache/puppeteer/chrome-headless-shell/mac_arm-150.0.7871.24/chrome-headless-shell-mac-arm64/chrome-headless-shell'
const ID = JSON.parse(fs.readFileSync(J + '/initdata.json', 'utf8'))
const TWA = 'http://localhost:5288/uk'
const sleep = (ms) => new Promise(r => setTimeout(r, ms))

// Тексты бота — дословно из uk_management_bot/config/locales/ru.json.
const T = {
  roleTitle: '👋 Добро пожаловать! Кто вы?\n\nЖитель — если вы живёте в доме.\nСотрудник — если менеджер выдал вам код приглашения.',
  welcome: '👋 Добро пожаловать в систему!\nСистема предназначена для жителей ЖК Olmazor Business City.\nПри регистрации обязательно предоставьте свой номер телефона и документ, подтверждающий право собственности, или договор аренды.\nС уважением, УК',
  phoneSaved: '✅ Телефон +998900000004 успешно сохранен!',
  formPrompt: '📝 Заполните форму регистрации жителя — нажмите кнопку ниже:',
  docsDesc: '📄 Обязательно приложите документ на квартиру: свидетельство о праве собственности (кадастровую выписку) или договор аренды. Документы временно хранятся в зашифрованном виде только на время проверки. После её завершения доступ к ним удаляется.',
  docsTitle: '📄 Загрузка документов',
  uploadFile: '📤 Загрузите файл документа:\n\nТип документа: Право собственности',
  docSaved: '✅ Документ успешно сохранен!\n\nТип: Право собственности\nФайл: photo.jpg',
  completed: '🎉 Профиль успешно заполнен!\n\n📊 Сводка загруженных документов:\n📄 Всего документов: 1\n- Право собственности: 1\n\n⏳ Ваша заявка отправлена на рассмотрение администратору. Ожидайте одобрения.',
  approved: '✅ Ваша заявка одобрена! Нажмите кнопку ниже для перезапуска бота.',
  restarted: '🔄 Бот был перезапущен. Выберите действие:',
}
const KB_DOC_TYPES = [['🏠 Право собственности', '📋 Договор аренды'], ['📄 Паспорт', '📄 Другие документы'], ['✅ Завершить онбординг']]
const KB_MENU = [['📝 Создать заявку', '📋 Мои заявки'], ['✅ Ожидают приёмки', '🚗 Контроль доступа'], ['👤 Профиль', 'ℹ️ Помощь'], ['📝 Обратная связь']]

const ANNOUNCEMENTS = {
  announcements: [
    { id: 'a1', type: 'info', title: 'Отключение горячей воды', body: '5 ноября с 10:00 до 16:00 в домах ул. Садовая, 12 и 14 — плановые работы.' },
    { id: 'contacts', type: 'contact', title: 'Контакты', body: 'Диспетчерская: +998 71 000-00-00\nАварийная служба: круглосуточно' }],
  working_hours: 'Пн–Пт: 08:00–20:00\nСб: 09:00–17:00\nВс: выходной', emergency_phones: [],
}

const browser = await puppeteer.launch({ executablePath: CH, args: ['--lang=ru-RU', '--allow-file-access-from-files'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 780, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
await page.setUserAgent('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36 Telegram-Android/11.2.0')
page.on('pageerror', e => console.log('PAGEERR', e.message))

// Кружок касания: виден на любом экране (переживает навигации).
await page.evaluateOnNewDocument(() => {
  window.__tap = (x, y) => {
    const d = document.createElement('div')
    d.style.cssText = `position:fixed;left:${x - 26}px;top:${y - 26}px;width:52px;height:52px;border-radius:50%;` +
      'background:rgba(68,194,74,.35);border:3px solid rgba(255,255,255,.95);box-shadow:0 0 0 2px rgba(0,0,0,.25);' +
      'z-index:2147483647;pointer-events:none;transform:scale(.5);transition:transform .35s ease-out,opacity .5s ease-in .55s'
    document.documentElement.appendChild(d)
    requestAnimationFrame(() => { d.style.transform = 'scale(1)'; d.style.opacity = '0' })
    setTimeout(() => d.remove(), 1200)
  }
})

await page.setRequestInterception(true)
page.on('request', async (r) => {
  const url = r.url()
  try {
    if (url.includes('/api/v2/announcements')) {
      return r.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(ANNOUNCEMENTS) })
    }
    // Регистрацию в БД не пишем: демо-житель остаётся pending для следующих съёмок.
    if (url.endsWith('/api/v2/registration/applicant') && r.method() === 'POST') {
      return r.respond({ status: 200, contentType: 'application/json', body: '{"status":"pending"}' })
    }
    // Служебный QA-двор в кадр не попадает.
    if (url.endsWith('/api/v2/registration/yards') && r.method() === 'GET') {
      const res = await fetch(url, { headers: r.headers() })
      const data = await res.json()
      const drop = (list) => list.filter(y => !String(y.name).includes('QA'))
      const body = Array.isArray(data) ? drop(data) : { ...data, items: drop(data.items || []) }
      return r.respond({ status: res.status, contentType: 'application/json', body: JSON.stringify(body) })
    }
  } catch (e) { console.log('INTERCEPT', url, e.message) }
  return r.continue()
})

const captions = []
let t0 = 0
const cap = async (text, minMs = 0) => {
  captions.push({ t: Date.now() - t0, text })
  console.log('cap', text)
  await sleep(minMs)
}
const tapEl = async (el, after = 700) => {
  await el.evaluate(n => n.scrollIntoView({ block: 'nearest' }))
  const b = await el.boundingBox()
  await page.evaluate((x, y) => window.__tap(x, y), b.x + b.width / 2, b.y + b.height / 2)
  await sleep(300)
  await el.click()
  await sleep(after)
}
const find = (text) => page.waitForSelector('::-p-text(' + text + ')', { timeout: 8000 })
const tap = async (text, after) => tapEl(await find(text), after)
const tapButton = async (exact, after) => {
  for (let i = 0; i < 20; i++) {
    for (const b of await page.$$('button')) {
      if ((await b.evaluate(n => n.innerText.trim())) === exact) return tapEl(b, after)
    }
    await sleep(250)
  }
  throw new Error('button not found: ' + exact)
}
const chat = (fn, ...args) => page.evaluate((f, a) => window.chat[f](...a), fn, args)
const card = async (k, h, p) => {
  const q = new URLSearchParams({ k, h, p })
  await page.goto('file://' + PP + '/card.html?' + q, { waitUntil: 'load' })
}
const openChat = async () => { await page.goto('file://' + PP + '/chat-player.html', { waitUntil: 'load' }); await sleep(300) }
const twa = async (tid, path) => {
  const hash = '#tgWebAppData=' + encodeURIComponent(ID[tid]) + '&tgWebAppVersion=7.10&tgWebAppPlatform=android&tgWebAppThemeParams=' +
    encodeURIComponent(JSON.stringify({ bg_color: '#ffffff', text_color: '#000000' }))
  await page.goto(TWA + path + hash, { waitUntil: 'networkidle0' })
  await sleep(600)
}

// Ролик: reg — регистрация, req — подача заявки.
const PART = process.argv[2]
if (!['reg', 'req'].includes(PART)) throw new Error('usage: node rec.mjs reg|req')
if (PART === 'reg') await card('Инструкция для жителей', 'Регистрация', 'Понадобятся номер телефона\nи документ на квартиру.')
else await card('Инструкция для жителей', 'Как подать заявку', 'Сантехника, электрика, лифт, уборка —\nвсё через мини-приложение в Telegram.')
// Кадры CDP со своими метками времени → точная синхронизация с субтитрами.
const FR = J + '/fr'
fs.rmSync(FR, { recursive: true, force: true }); fs.mkdirSync(FR)
const frames = []
const cdp = await page.createCDPSession()
cdp.on('Page.screencastFrame', ({ data, metadata, sessionId }) => {
  const name = String(frames.length).padStart(5, '0') + '.jpg'
  fs.writeFileSync(FR + '/' + name, Buffer.from(data, 'base64'))
  frames.push({ name, ts: metadata.timestamp * 1000 })
  cdp.send('Page.screencastFrameAck', { sessionId }).catch(() => {})
})
t0 = Date.now()
await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: 780, maxHeight: 1560 })
const rec = {
  stop: async () => {
    await cdp.send('Page.stopScreencast')
    const end = Date.now()
    const lines = frames.map((f, i) => `file '${FR}/${f.name}'\nduration ${(((frames[i + 1]?.ts ?? end) - f.ts) / 1000).toFixed(3)}`)
    // Первый кадр тянем от t0, чтобы ось времени совпала с субтитрами.
    lines.unshift(`file '${FR}/${frames[0].name}'\nduration ${((frames[0].ts - t0) / 1000).toFixed(3)}`)
    lines.push(`file '${FR}/${frames[frames.length - 1].name}'`)
    fs.writeFileSync(J + '/frames.txt', lines.join('\n') + '\n')
  },
}
await sleep(400)

// ── Часть 1. Регистрация ────────────────────────────────────────────────
if (PART === 'reg') {
await cap('Регистрация занимает около минуты', 1800)

await openChat()
await chat('me', '/start'); await sleep(400)
await chat('bot', T.roleTitle, ['🏠 Я житель', '🧰 Я сотрудник (по приглашению)'])
await cap('Отправьте боту /start и нажмите «Я житель»', 2400)
await tap('Я житель', 400)
await chat('bot', T.welcome, null, '09:31')
await chat('kb', [['📱 Поделиться контактом'], ['📝 Регистрация (форма)']])
await cap('Нажмите «Поделиться контактом» и подтвердите. Без телефона регистрация невозможна', 2700)
await tap('Поделиться контактом', 300)
await chat('dialog', 'Поделиться номером телефона?', 'Бот получит ваш номер телефона.', ['ОТМЕНА', 'OK']); await sleep(700)
await tap('OK', 200)
await chat('closeDialog')
await chat('me', '👤 Азиз Каримов\n+998 90 000-00-04', '09:31'); await sleep(300)
await chat('bot', T.phoneSaved, null, '09:31')
await chat('kb', [['🏠 Выбрать квартиру'], ['📝 Регистрация (форма)']]); await sleep(1200)
await cap('Затем «Регистрация (форма)» → «Открыть форму»', 1200)
await tap('Регистрация (форма)', 300)
await chat('me', '📝 Регистрация (форма)', '09:32'); await sleep(300)
await chat('bot', T.formPrompt, ['🔗 Открыть форму'], '09:32'); await sleep(600)
await tap('Открыть форму', 200)

await twa('920000004', '/register')
await cap('Выберите двор, дом и квартиру', 700)
await tap('Северный', 600)
await tap('Садовая, 12', 600)
await page.type('input', '15', { delay: 120 }); await sleep(400)
await tapButton('15', 600)
await cap('Проверьте данные и нажмите «Отправить заявку»', 1800)
await tap('Отправить заявку', 1500)

await openChat()
await chat('bot', T.welcome, null, '09:31')
await chat('kb', [['🏠 Выбрать квартиру'], ['📝 Регистрация (форма)']])
await chat('bot', T.docsDesc, ['📤 Загрузить документы'], '09:34')
await cap('Вернитесь в чат и нажмите «Загрузить документы»', 2600)
await tap('Загрузить документы', 300)
await chat('bot', T.docsTitle + '\n\n' + T.docsDesc, null, '09:34')
await chat('kb', KB_DOC_TYPES); await sleep(300)
await cap('Выберите «Право собственности» или «Договор аренды» и отправьте фото документа', 2700)
await tap('🏠 Право собственности', 300)
await chat('me', '🏠 Право собственности', '09:35')
await chat('bot', T.uploadFile, null, '09:35'); await sleep(700)
await chat('photo', '📷 фото документа', '09:35'); await sleep(1000)
await chat('unphoto')
await chat('note', 'Бот удалил фото из чата')
await chat('bot', T.docSaved, null, '09:35')
await chat('kb', [['📄 Добавить еще документы', '✅ Завершить онбординг']]); await sleep(800)
await cap('Нажмите «Завершить онбординг» и дождитесь проверки', 1700)
await tap('Завершить онбординг', 300)
await chat('me', '✅ Завершить онбординг', '09:36')
await chat('bot', T.completed, null, '09:36'); await chat('kb', null); await sleep(1500)
await chat('note', 'Позже — после проверки')
await chat('bot', T.approved, ['🔄 Перезапустить бота'], '14:05')
await cap('После одобрения нажмите «Перезапустить бота» — готово!', 1500)
await tap('Перезапустить бота', 300)
await chat('bot', T.restarted, null, '14:06')
await chat('kb', KB_MENU); await sleep(2500)
}

if (PART === 'req') {
await cap('Подать заявку — меньше минуты', 1800)
await openChat()
await chat('bot', T.restarted, null, '14:06')
await chat('kb', KB_MENU)
await cap('Откройте приложение кнопкой «Приложение»', 1500)
await tap('Приложение', 200)

await twa('920000001', '/twa/app')
await page.evaluate(() => sessionStorage.clear())
await cap('Вкладка «Создать» → выберите, что случилось', 1200)
await tap('Создать', 700)
await tap('Сантехника', 700)
await cap('Выберите адрес: квартира, дом или двор', 1800)
await tap('кв. 15', 600)
await cap('Опишите проблему', 300)
await (await page.$('textarea')).type('Засор в ванной, вода уходит медленно.', { delay: 35 })
await sleep(500)
await tapButton('Далее', 600)
await cap('Фото — по желанию, до 5 штук', 1800)
await tapButton('Далее', 600)
await cap('Выберите срочность. «Критическая» — только при аварии', 3200)
await tap('Средняя', 600)
await cap('Проверьте и нажмите «Отправить заявку»', 1800)
await tapButton('Отправить заявку', 1200)
await cap('Заявка создана. Статус видно на вкладке «Заявки», бот сообщит о каждом изменении', 3800)
try { await tap('Засор в ванной', 1500) } catch (e) { console.log('SKIP detail', e.message) }

await card('Готово', 'Спасибо!', 'Срочные проблемы — сразу звоните\nдиспетчеру управляющей компании.')
await cap('При аварии — сразу звоните диспетчеру', 3200)
}
captions.push({ t: Date.now() - t0, text: '' })
await rec.stop()
fs.writeFileSync(J + '/captions.json', JSON.stringify(captions, null, 1))
await browser.close()
console.log('done', (Date.now() - t0) / 1000, 's')
