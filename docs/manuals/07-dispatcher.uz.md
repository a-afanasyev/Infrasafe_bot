# Dispetcher uchun qo'llanma

> _Oxirgi tahrir: 2026-11-13_ · DOCX: `ProFK_Инструкция_диспетчера_v2.0.0_2026-11-13_uz.docx`

Bu qo'llanma telefon orqali yashovchilardan ariza qabul qiladigan xodim uchun. Sizning vazifangiz — qo'ng'iroq qilgan odamni tinglash va uning muammosini to'g'ri manzil bilan arizaga yozish.

## Dispetcher kim

- Siz arizani **telefon qo'ng'irog'i bo'yicha** yaratasiz: yashovchi qo'ng'iroq qiladi, siz uning so'zlaridan ariza to'ldirasiz.
- Siz majmuaning **istalgan hovlisi, uyi va xonadoni** bo'yicha ariza yaratasiz.
- Siz arizalarni bajarmaysiz va qabul qilmaysiz. Bu bilan ijrochilar va menejerlar shug'ullanadi.
- Siz faqat Telegram'da ishlaysiz. Veb-dashbord dispetcher uchun ochiq emas.

## Nimadan boshlash kerak

1. Menejer sizga «Dispetcher» roliga taklif havolasini yuboradi.
2. Siz havolani ochasiz va botda ro'yxatdan o'tasiz.
3. Menejer hisob yozuvingizni tasdiqlaydi. Ariza qabul qilish **faqat tasdiqlangandan keyin** mumkin.
4. Tasdiqlangandan keyin botga `/start` yuboring — menyu yangilanadi.

## Botdagi asosiy menyu

- **«📞 Qo'ng'iroq bo'yicha ariza»** — ariza qabul qilish. Asosiy ish tugmasi.
- **«👤 Profil»**, **«ℹ️ Yordam»**, **«📝 Qayta aloqa»**.
- **«🔀 Rolni tanlash»** — agar sizda bir nechta rol bo'lsa.

Agar tugma ko'rinmasa — botga `/start` yuboring. Baribir ko'rinmasa, menejer hisob yozuvingizni hali tasdiqlamagan.

## Arizani qanday qabul qilish

1. Botda **«📞 Qo'ng'iroq bo'yicha ariza»**ni bosing.
2. Bot xabar yuboradi. Undagi **«🔗 Formani ochish»** tugmasini bosing — ariza ekrani ochiladi.

Ekranda har safar **bitta savol** chiqadi. Javob bering — keyingi savol ochiladi. Oldingi savolga qaytish uchun yuqoridagi **«Orqaga»**ni bosing.

### 1-qadam. Qo'ng'iroq qiluvchining telefoni

Qo'ng'iroq qilgan odamdan telefon raqamini so'rang va raqamlarni kiriting. Keyin **«Keyingi»**ni bosing.

Tizim shu raqam bo'yicha yashovchini o'zi qidiradi:

- **Yashovchi topildi.** Ekranda uning ismi chiqadi: «Qo'ng'iroq qilayotgan shu kishimi?». Agar shu odam bo'lsa — ismini bosing. Boshqa odam bo'lsa — **«Yo'q, boshqa odam»**ni bosing.
- **Yashovchi topilmadi.** Ekran ismni so'raydi: «Qo'ng'iroq qiluvchining ismi nima?». Ismni yozing va **«Keyingi»**ni bosing. Ismni bilmasangiz, bo'sh qoldirsa ham bo'ladi.

### 2-qadam. Muammo qayerda

Manzil **faqat ro'yxatdan** tanlanadi. Manzilni qo'lda yozib bo'lmaydi.

- Agar yashovchi topilgan bo'lsa, ekranda **uning xonadoni** chiqadi. Muammo shu xonadonda bo'lsa — uni bosing. Boshqa joyda bo'lsa — **«Boshqa manzil»**ni bosing.
- Aks holda manzilni ketma-ket tanlang:
  1. **Hovli** — «Hovlini tanlang».
  2. **Uy** — «Uyni tanlang».
  3. **Xonadon** — «Xonadon raqami». Xonadonlar ko'p bo'lsa, raqamni yuqoridagi maydonga yozing — ro'yxat qisqaradi.

Muammo xonadonda emas, umumiy joyda bo'lsa:

- **«Butun uy (yo'lak, tom, yerto'la)»** — muammo uyning umumiy qismida: yo'lak, lift, tom, yerto'la.
- **«Butun hovli (aniq uy emas)»** — muammo hovlida: yoritish, o'yin maydonchasi, axlat.

Noto'g'ri hovli yoki uyni tanlagan bo'lsangiz — pastdagi **«Boshqa hovli»** yoki **«Boshqa uy»**ni bosing.

> **Muhim.** Qo'ng'iroq qiluvchidan uy raqamini va xonadon raqamini aniq so'rang. Noto'g'ri manzil bilan yaratilgan ariza ijrochini boshqa joyga yuboradi.

### 3-qadam. Nima bo'ldi

Muammo turini tanlang:

| Toifa | Qachon tanlanadi |
| --- | --- |
| Elektrika | chiroq yonmayapti, rozetka ishlamayapti, tok yo'q |
| Santexnika | suv oqyapti, quvur yorilgan, kanalizatsiya tiqilgan |
| Isitish | batareya sovuq, isitish yo'q |
| Ventilyatsiya | havo tortmayapti |
| Lift | lift ishlamayapti yoki to'xtab qolgan |
| Tozalash | yo'lak yoki hovli iflos |
| Obodonlashtirish | daraxt, gazon, sug'orish, hovli |
| Xavfsizlik | eshik, domofon, shlagbaum |
| Internet/TV | internet yoki televideniye |
| Ta'mirlash | boshqa ta'mirlash ishlari |
| Boshqa | hech biri mos kelmasa |

### 4-qadam. Muammoni yozing

Qo'ng'iroq qiluvchining so'zlaridan qisqa va aniq yozing: **nima buzildi va aynan qayerda**.

- Yaxshi: «Oshxonada rakovina ostidagi quvur oqyapti».
- Yomon: «Suv», «Buzildi», «Keling».

Yozib bo'lgach **«Keyingi»**ni bosing.

### 5-qadam. Qanchalik shoshilinch

| Tanlov | Qachon |
| --- | --- |
| Oddiy | kutish mumkin, xavf yo'q |
| O'rta | noqulay, lekin xavfli emas |
| Shoshilinch | bugun hal qilish kerak |
| Kritik | hayot yoki mulkka xavf: suv bosishi, yong'in, gaz hidi |

### 6-qadam. Arizani tekshiring

Ekranda butun ariza chiqadi: qo'ng'iroq qiluvchi, manzil, toifa, tavsif, shoshilinchlik. Hammasini o'qib chiqing.

- Xato topsangiz — **o'sha qatorni bosing** va to'g'rilang. Keyin yana shu ekranga qaytasiz.
- Hammasi to'g'ri bo'lsa — **«Yuborish»**ni bosing.

Ekranda **«… ariza qabul qilindi»** yozuvi va ariza raqami chiqadi. Raqamni qo'ng'iroq qiluvchiga ayting. Keyingi qo'ng'iroq uchun **«Yangi ariza»**ni bosing.

## Tizim eslatmalari

«Yuborish»ni bosganingizda tizim arizani tekshiradi. Agar biror narsa mos kelmasa, ekranning yuqorisida **sariq eslatma** chiqadi. Bu xato emas — bu maslahat. Uni o'qing va qaror qiling.

| Eslatma | Bu nimani anglatadi | Nima qilish kerak |
| --- | --- | --- |
| «Tavsifga ko'ra bu ko'proq «…» ga o'xshaydi» | Toifa tavsifga mos kelmayapti | **«Tuzatish»** — toifa o'zi almashadi |
| «Tavsifga ko'ra bu shoshilinchroq: «…»» | Shoshilinchlik past tanlangan | **«Tuzatish»** — shoshilinchlik o'zi ko'tariladi |
| «Tavsifda boshqa manzil aytilgan. To'g'risini tanlang:» | Tavsifdagi uy tanlangan uydan farq qiladi | Qo'ng'iroq qiluvchidan manzilni qayta so'rang va to'g'ri uyni bosing |
| «Muammo xonadon ichida ko'rinadi. Xonadon raqamini so'rang.» | Butun uy tanlangan, lekin muammo xonadonda | **«Tuzatish»**ni bosing va xonadonni tanlang |
| «Tavsifdan nima bo'lgani tushunarsiz…» | Tavsif juda qisqa yoki noaniq | **«Tuzatish»**ni bosing va tavsifni to'liqroq yozing |

Har bir eslatmada ikkita tugma bor:

- **«Tuzatish»** — tizim taklifini qabul qilish.
- **«Shunday qolsin»** — o'zingiz tanlaganingizni qoldirish. Agar ishonchingiz komil bo'lsa, shuni bosing.

Eslatmalardan keyin **«Yuborish»** yoki **«Shundayligicha yuborish»**ni bosing — ariza yuboriladi. Tizim sizni to'xtatib qo'ymaydi: oxirgi qaror sizniki.

Agar eslatma chiqmasa — hammasi joyida, ariza darhol yuboriladi.

## Arizadan keyin nima bo'ladi

- Ariza darhol menejerlar taxtasida paydo bo'ladi va ijrochiga yuboriladi.
- Agar yashovchi telefon raqami bo'yicha topilgan bo'lsa, ariza **uning nomidan** yaratiladi va u arizani o'z ilovasida ko'radi.
- Agar yashovchi topilmagan bo'lsa, qo'ng'iroq qiluvchining ismi va telefoni arizaga izoh sifatida yoziladi. Xonadon tanlangan bo'lsa, shu xonadonda ro'yxatdan o'tgan yashovchilar ham arizani ko'radi — «📞 Qo'ng'iroq bo'yicha qabul qilingan» belgisi bilan.
- Bunday ariza bo'yicha ishni menejer qabul qiladi.

## Ko'p beriladigan savollar

| Vaziyat | Nima qilish kerak |
| --- | --- |
| Botda «📞 Qo'ng'iroq bo'yicha ariza» tugmasi yo'q | Botga `/start` yuboring. Yordam bermasa — menejer hisob yozuvingizni tasdiqlashini kuting |
| Menyuda eski tugmalar ko'rinyapti (masalan, ijrochi menyusi) | Botga `/start` yuboring — menyu yangilanadi |
| Ekranda «🔒 Ilovani Telegram-bot orqali oching» chiqdi | Ekranni yoping va botdagi «🔗 Formani ochish» tugmasi orqali qayta oching |
| Yashovchi telefon bo'yicha topilmadi | Bu odatiy hol: u boshqa raqamdan qo'ng'iroq qilgan yoki ro'yxatdan o'tmagan. Ismini yozing va manzilni ro'yxatdan tanlang |
| Kerakli hovli, uy yoki xonadon ro'yxatda yo'q | Faqat faol obyektlar ko'rsatiladi. Menejerga xabar bering |
| Qo'ng'iroq qiluvchi xonadon raqamini bilmaydi | «Butun uy»ni tanlang va tafsilotni tavsifga yozing: qavat, yo'lak |
| Arizani yuborgandan keyin xato topdim | Arizani o'zgartira olmaysiz. Ariza raqamini menejerga ayting |
| Arizaning holatini ko'rmoqchiman | Dispetcherda arizalar ro'yxati yo'q. Holatni menejerdan so'rang |
| Bir daqiqada juda ko'p ariza kiritdim va xatolik chiqdi | Bir oz kuting va qayta urinib ko'ring |
| «Yuborish»ni bosdim, lekin qizil xatolik chiqdi | Internetni tekshiring va «Yuborish»ni yana bosing. Takrorlansa — menejerga xabar bering |
