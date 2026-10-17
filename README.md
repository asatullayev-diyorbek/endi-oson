# Endi Oson

Qurilmalar orasida fayllarni **100% lokal tarmoq** ichida uzatish xizmati,
**Telegram orqali kirish** bilan.

To'liq implementatsiya rejasi: `docs/PLAN.md`. Deploy qo'llanmasi (Render.com): `docs/DEPLOY_RENDER.md`.

## Hozirgi holat (0–6-bosqich)

- Django loyiha skeleti (ASGI, Channels, custom `User` modeli).
- Telegram orqali bir martalik token login oqimi: `/auth/telegram/login/`.
- Qurilmalar: real-time onlayn ro'yxat va nom berish — `/devices/` (`ws/devices/`).
- Ulanish rozilik: qurilmalar orasida so'rov/qabul/rad etish, 30s timeout.
- Lokal-only WebRTC: STUN/TURN'siz `RTCPeerConnection`, signaling faqat
  tasdiqlangan ulanish doirasida relay qilinadi, `getStats()` orqali
  host-candidate + private-IPv4 davomiy tekshiruvi, muvaffaqiyatsiz bo'lsa
  `TransferLog.rejected_non_local` audit yozuvi (`/transfers/log/`).
- Fayl uzatish: DataChannel orqali bo'lak-bo'lak (chunk) yuborish,
  backpressure (`bufferedAmountLowThreshold`), progress bar, CRC32 yaxlitlik
  tekshiruvi va bekor qilish — hammasi `/devices/` sahifasida.

## Lokal ishga tushirish

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env   # SECRET_KEY, TELEGRAM_BOT_TOKEN va boshqalarni to'ldiring

# PostgreSQL va Redis kerak (dev uchun): docker compose up -d
python manage.py migrate
python manage.py createsuperuser

# HTTP-only tekshirish uchun:
python manage.py runserver

# WebSocket (qurilmalar, ulanish so'rovi) ishlashi uchun to'liq ASGI server kerak:
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

Telegram bot'ni alohida process sifatida ishga tushirish:

```bash
python manage.py runbot
```

## Testlar

```bash
pytest                       # Django/Channels backend
node --test static/js/*.test.js  # Lokal-only tekshiruv + fayl uzatish protokoli (JS)
```

## Muhim cheklov: "100% lokal" kafolati

Fayl uzatish bosqichi (5–6) WebRTC orqali, STUN/TURN serversiz, faqat host
candidate'lar bilan ishlaydi va `getStats()` orqali tanlangan candidate
juftligi tekshiriladi. Bu **amaliy darajada ishonchli**, lekin brauzer
xavfsizlik modeli tufayli OS tarmoq interfeysini to'liq dasturiy nazorat
qilish imkonsiz — shuning uchun matematik 100% kafolat emas. Qat'iy kafolat
kerak bo'lsa, kelajakda ixtiyoriy lokal agent qo'shiladi (`docs/PLAN.md`
dagi roadmap).
