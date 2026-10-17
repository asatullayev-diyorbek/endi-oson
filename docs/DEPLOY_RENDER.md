# Render.com'ga deploy qilish

Nega Vercel emas: ilova WebSocket (Django Channels — qurilmalar presence,
ulanish so'rovi, WebRTC signaling) va doimiy ishlaydigan Telegram bot
process'iga tayanadi. Vercel'ning serverless Python funksiyalari ikkisini
ham qo'llamaydi. Render uzoq muddatli ASGI (Daphne) web-servisi + alohida
background worker'ni birga ishlatishga imkon beradi — shuning uchun tanlandi.

## 1. Oldindan kerak bo'ladigan narsalar

- Telegram bot yaratilgan va tokeni qo'lda ([@BotFather](https://t.me/BotFather)).
- Bu repo GitHub'da (`asatullayev-diyorbek/endi-oson`) — Render shu orqali ulanadi.

## 2. Blueprint orqali deploy

1. [render.com](https://render.com) da ro'yxatdan o'tib GitHub akkauntingizni ulang.
2. Dashboard → **New** → **Blueprint** → `asatullayev-diyorbek/endi-oson` repo'ni tanlang.
3. Render `render.yaml` faylini avtomatik topadi va 4 resurs taklif qiladi:
   - `endi-oson-web` — Daphne (HTTP + WebSocket), bepul tarif
   - `endi-oson-bot` — Telegram bot (worker), **pullik "starter" tarif majburiy** (Render'da worker uchun bepul tarif yo'q)
   - `endi-oson-db` — PostgreSQL, bepul tarif (~30 kundan keyin muddati tugaydi, keyin yangilash kerak bo'ladi)
   - `endi-oson-redis` — Key Value (Redis-compatible), bepul tarif
4. **Apply**'dan oldin quyidagi "sync: false" maydonlarni ikki servis (`endi-oson-web` va `endi-oson-bot`) uchun ham to'ldiring:
   - `TELEGRAM_BOT_TOKEN` — botingizning tokeni
   - `TELEGRAM_BOT_USERNAME` — botingiz username'i (`@` belgisiz, masalan `EndiOsonBot`)
5. **Apply**'ni bosing. Birinchi deploy ~5-10 daqiqa davom etadi (build + migratsiya).

## 3. Deploy'dan keyin

- `endi-oson-web` servisining haqiqiy URL'ini tekshiring (odatda
  `https://endi-oson-web.onrender.com`, lekin nom band bo'lsa Render boshqa
  pastki domen beradi). Agar `render.yaml`dagi `SITE_ORIGIN` qiymatidan farq
  qilsa, shu servisning **Environment** bo'limida `SITE_ORIGIN`ni to'g'ri
  URL bilan yangilang va qayta deploy qiling.
- Superuser yaratish: Render dashboard → `endi-oson-web` → **Shell** →
  `python manage.py createsuperuser`.
- `https://<domen>/auth/telegram/login/` orqali to'liq login oqimini sinab ko'ring.

## 4. Muhim cheklovlar (ochiq va aytib qo'yilgan)

- **Bepul `web` servisi 15 daqiqa harakatsizlikdan keyin "uxlaydi".**
  Keyingi so'rovda sovuq boshlanish bo'ladi va bu paytda ochiq WebSocket
  ulanishlari (qurilmalar presence, signaling) uziladi. Jiddiy/doimiy
  foydalanish uchun `endi-oson-web`ni Render dashboard'da **Starter**
  tarifga o'tkazish tavsiya etiladi.
- **Bepul PostgreSQL ~30 kundan keyin muddati tugaydi** — Render oldindan
  ogohlantiradi, kerak bo'lsa pullik tarifga o'tkazish yoki yangi baza
  yaratib migratsiya qilish lozim.
- **`endi-oson-bot` (worker) uchun bepul tarif yo'q** — bu Render'ning
  umumiy siyosati, loyihaga xos emas.
- Fayl uzatishning o'zi (WebRTC DataChannel) serverdan butunlay chetlab
  o'tadi — bu cheklovlar faqat login/presence/signaling kabi server
  orqali o'tadigan qismlarga tegishli.
