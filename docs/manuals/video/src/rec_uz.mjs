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
  roleTitle: "👋 Xush kelibsiz! Siz kimsiz?\n\nRezident — agar shu uyda yashasangiz.\nXodim — agar menejer sizga taklif kodini bergan bo'lsa.",
  welcome: "👋 Tizimga xush kelibsiz!\nTizim Olmazor Business City turar-joy majmuasi aholisi uchun mo'ljallangan.\nRo'yxatdan o'tishda telefon raqamingizni va mulk huquqini tasdiqlovchi hujjatni yoki ijara shartnomasini taqdim etish majburiy.\nHurmat bilan, Boshqaruv kompaniyasi",
  phoneSaved: '✅ Telefon +998900000004 saqlandi!',
  formPrompt: "📝 Turar joy egasi ro'yxatdan o'tish formasini to'ldiring — quyidagi tugmani bosing:",
  docsDesc: "📄 Kvartira hujjatini albatta ilova qiling: mulk huquqi guvohnomasi (kadastr ko'chirmasi) yoki ijara shartnomasi. Hujjatlar faqat tekshiruv vaqtida shifrlangan holda vaqtincha saqlanadi. Tekshiruv tugagach, ularga kirish o'chiriladi.",
  docsTitle: '📄 Hujjatlar yuklanmoqda',
  uploadFile: '📤 Hujjat faylini yuklash:\n\nHujjat turi: Mulk huquqi',
  docSaved: '✅ Hujjat muvaffaqiyatli saqlandi!\n\nTuri: Mulk huquqi\nFayl: photo.jpg',
  completed: "🎉 Ro'yxatdan o'tish tugallandi! Sizning ma'lumotlaringiz:\n\n📊 Yuklangan hujjatlarning qisqacha mazmuni:\n📄 Jami hujjatlar: 1\n- Mulk huquqi: 1\n\n⏳ Arizangiz moderatsiyaga yuborildi. Administrator tasdiqlashidan keyin arizalar yaratishingiz mumkin.",
  approved: '✅ Arizangiz tasdiqlandi! Botni qayta ishga tushirish uchun quyidagi tugmani bosing.',
  restarted: '🔄 Bot qayta ishga tushirildi. Amalni tanlang:',
}
const KB_DOC_TYPES = [['🏠 Mulk huquqi', '📋 Ijara shartnomasi'], ['📄 Pasport', '📄 Boshqa hujjatlar'], ["✅ Ro'yxatdan o'tishni yakunlash"]]
const KB_MENU = [['📝 Ariza yaratish', '📋 Mening arizalarim'], ['✅ Qabul qilish kutilmoqda', '🚗 Kirish nazorati'], ['👤 Profil', 'ℹ️ Yordam'], ['📝 Qayta aloqa']]

const ANNOUNCEMENTS = {
  announcements: [
    { id: 'a1', type: 'info', title: "Issiq suv o'chiriladi", body: "5-noyabr kuni 10:00 dan 16:00 gacha Sadovaya ko'chasi, 12 va 14-uylarda rejali ishlar." },
    { id: 'contacts', type: 'contact', title: 'Kontaktlar', body: 'Dispetcherlik: +998 71 000-00-00\nAvariya xizmati: kecha-kunduz' }],
  working_hours: 'Du–Ju: 08:00–20:00\nSha: 09:00–17:00\nYak: dam olish kuni', emergency_phones: [],
}

const browser = await puppeteer.launch({ executablePath: CH, args: ['--lang=uz-UZ', '--allow-file-access-from-files'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 780, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
await page.setUserAgent('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36 Telegram-Android/11.2.0')
page.on('pageerror', e => console.log('PAGEERR', e.message))

// Кружок касания: виден на любом экране (переживает навигации).
await page.evaluateOnNewDocument(() => { try { localStorage.setItem('i18nextLng', 'uz') } catch (e) {} })
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
const openChat = async () => { await page.goto('file://' + PP + '/chat-player-uz.html', { waitUntil: 'load' }); await sleep(300) }
const twa = async (tid, path) => {
  const hash = '#tgWebAppData=' + encodeURIComponent(ID[tid]) + '&tgWebAppVersion=7.10&tgWebAppPlatform=android&tgWebAppThemeParams=' +
    encodeURIComponent(JSON.stringify({ bg_color: '#ffffff', text_color: '#000000' }))
  await page.goto(TWA + path + hash, { waitUntil: 'networkidle0' })
  await sleep(600)
}

// Ролик: reg — регистрация, req — подача заявки.
const PART = process.argv[2]
if (!['reg', 'req'].includes(PART)) throw new Error('usage: node rec.mjs reg|req')
if (PART === 'reg') await card("Aholi uchun yo'riqnoma", "Ro'yxatdan o'tish", "Telefon raqami va kvartira\nhujjati kerak bo'ladi.")
else await card("Aholi uchun yo'riqnoma", 'Ariza qanday beriladi', 'Santexnika, elektrika, lift, tozalash —\nhammasi Telegramdagi mini-ilova orqali.')
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
await cap("Ro'yxatdan o'tish taxminan bir daqiqa oladi", 2500)

await openChat()
await chat('me', '/start'); await sleep(400)
await chat('bot', T.roleTitle, ['🏠 Men rezidentman', "🧰 Men xodimman (taklif bo'yicha)"])
await cap('Botga /start yuboring va «Men rezidentman» tugmasini bosing', 3400)
await tap('Men rezidentman', 400)
await chat('bot', T.welcome, null, '09:31')
await chat('kb', [['📱 Kontaktni ulashish'], ["📝 Ro'yxatdan o'tish (forma)"]])
await cap("«Kontaktni ulashish» tugmasini bosing va tasdiqlang. Telefonsiz ro'yxatdan o'tib bo'lmaydi", 3200)
await tap('Kontaktni ulashish', 300)
await chat('dialog', 'Telefon raqamini ulashasizmi?', 'Bot telefon raqamingizni oladi.', ['BEKOR QILISH', 'OK']); await sleep(700)
await tap('OK', 200)
await chat('closeDialog')
await chat('me', '👤 Азиз Каримов\n+998 90 000-00-04', '09:31'); await sleep(300)
await chat('bot', T.phoneSaved, null, '09:31')
await chat('kb', [['🏠 Kvartira tanlash'], ["📝 Ro'yxatdan o'tish (forma)"]]); await sleep(1200)
await cap("So'ng «Ro'yxatdan o'tish (forma)» → «Formani ochish»", 1200)
await tap("Ro'yxatdan o'tish (forma)", 300)
await chat('me', "📝 Ro'yxatdan o'tish (forma)", '09:32'); await sleep(300)
await chat('bot', T.formPrompt, ['🔗 Formani ochish'], '09:32'); await sleep(600)
await tap('Formani ochish', 200)

await twa('920000004', '/register')
await cap('Hovli, uy va kvartirani tanlang', 700)
await tap('Северный', 600)
await tap('Садовая, 12', 600)
await page.type('input', '15', { delay: 120 }); await sleep(400)
await tapButton('15', 600)
await cap("Ma'lumotlarni tekshiring va «Arizani yuborish» tugmasini bosing", 2400)
await tap('Arizani yuborish', 1500)

await openChat()
await chat('bot', T.welcome, null, '09:31')
await chat('kb', [['🏠 Kvartira tanlash'], ["📝 Ro'yxatdan o'tish (forma)"]])
await chat('bot', T.docsDesc, ['📤 Hujjatlarni yuklash'], '09:34')
await cap('Chatga qayting va «Hujjatlarni yuklash» tugmasini bosing', 3200)
await tap('Hujjatlarni yuklash', 300)
await chat('bot', T.docsTitle + '\n\n' + T.docsDesc, null, '09:34')
await chat('kb', KB_DOC_TYPES); await sleep(300)
await cap('«Mulk huquqi» yoki «Ijara shartnomasi»ni tanlang va hujjat rasmini yuboring', 2700)
await tap('🏠 Mulk huquqi', 300)
await chat('me', '🏠 Mulk huquqi', '09:35')
await chat('bot', T.uploadFile, null, '09:35'); await sleep(700)
await chat('photo', '📷 hujjat rasmi', '09:35'); await sleep(1000)
await chat('unphoto')
await chat('note', "Bot rasmni chatdan o'chirdi")
await chat('bot', T.docSaved, null, '09:35')
await chat('kb', [["📄 Yana hujjatlar qo'shish", "✅ Ro'yxatdan o'tishni yakunlash"]]); await sleep(800)
await cap("«Ro'yxatdan o'tishni yakunlash» tugmasini bosing va tekshiruvni kuting", 3000)
await tap("Ro'yxatdan o'tishni yakunlash", 300)
await chat('me', "✅ Ro'yxatdan o'tishni yakunlash", '09:36')
await chat('bot', T.completed, null, '09:36'); await chat('kb', null); await sleep(1500)
await chat('note', "Keyinroq — tekshiruvdan so'ng")
await chat('bot', T.approved, ['🔄 Botni qayta ishga tushirish'], '14:05')
await cap('Tasdiqlangach, «Botni qayta ishga tushirish» tugmasini bosing — tayyor!', 2100)
await tap('Botni qayta ishga tushirish', 300)
await chat('bot', T.restarted, null, '14:06')
await chat('kb', KB_MENU); await sleep(2500)
}

if (PART === 'req') {
await cap('Ariza berish bir daqiqadan kam vaqt oladi', 2700)
await openChat()
await chat('bot', T.restarted, null, '14:06')
await chat('kb', KB_MENU)
await cap('Kiritish maydoni yonidagi «Ilova» tugmasi bilan ilovani oching', 1500)
await tap('Ilova', 200)

await twa('920000001', '/twa/app')
await page.evaluate(() => sessionStorage.clear())
await cap("«Yaratish» bo'limi → nima bo'lganini tanlang", 1200)
await tap('Yaratish', 700)
await tap('Santexnika', 700)
await cap('Manzilni tanlang: kvartira, uy yoki hovli', 2200)
await tap('кв. 15', 600)
await cap('Muammoni tasvirlab bering', 300)
await (await page.$('textarea')).type('Vannada tiqilib qoldi, suv sekin ketyapti.', { delay: 35 })
await sleep(500)
await tapButton('Keyingisi', 600)
await cap('Rasm — ixtiyoriy, 5 tagacha', 1800)
await tapButton('Keyingisi', 600)
await cap("Shoshilinchlikni tanlang. «Kritik» — faqat avariya bo'lganda", 3600)
await tap("O'rta", 600)
await cap('Tekshiring va «Ariza yuborish» tugmasini bosing', 2100)
await tapButton('Ariza yuborish', 1200)
await cap("Ariza yaratildi. Holatini «Arizalar» bo'limida ko'rasiz, bot har bir o'zgarish haqida xabar beradi", 5300)
try { await tap('Vannada tiqilib', 1500) } catch (e) { console.log('SKIP detail', e.message) }

await card('Tayyor', 'Rahmat!', "Shoshilinch muammolarda darhol boshqaruv\nkompaniyasi dispetcheriga qo'ng'iroq qiling.")
await cap("Avariya bo'lsa — darhol dispetcherga qo'ng'iroq qiling", 4000)
}
captions.push({ t: Date.now() - t0, text: '' })
await rec.stop()
fs.writeFileSync(J + '/captions_uz.json', JSON.stringify(captions, null, 1))
await browser.close()
console.log('done', (Date.now() - t0) / 1000, 's')
