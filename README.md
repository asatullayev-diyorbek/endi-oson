# Endi Oson

Qurilmalar orasida fayllarni **100% lokal tarmoq** ichida uzatish xizmati,
**Telegram orqali kirish** bilan.

To'liq implementatsiya rejasi: `docs/PLAN.md`.

## Hozirgi holat (0–2-bosqich)

- Django loyiha skeleti (ASGI, Channels tayyor, custom `User` modeli).
- Telegram orqali bir martalik token login oqimi: `/auth/telegram/login/`.
- Qurilmalar, signaling va fayl uzatish keyingi bosqichlarda qo'shiladi.

## Lokal ishga tushirish

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env   # SECRET_KEY, TELEGRAM_BOT_TOKEN va boshqalarni to'ldiring

# PostgreSQL va Redis kerak (dev uchun): docker compose up -d
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Telegram bot'ni alohida process sifatida ishga tushirish:

```bash
python manage.py runbot
```

## Testlar

```bash
pytest
```

## Muhim cheklov: "100% lokal" kafolati

Fayl uzatish bosqichi (5–6) WebRTC orqali, STUN/TURN serversiz, faqat host
candidate'lar bilan ishlaydi va `getStats()` orqali tanlangan candidate
juftligi tekshiriladi. Bu **amaliy darajada ishonchli**, lekin brauzer
xavfsizlik modeli tufayli OS tarmoq interfeysini to'liq dasturiy nazorat
qilish imkonsiz — shuning uchun matematik 100% kafolat emas. Qat'iy kafolat
kerak bo'lsa, kelajakda ixtiyoriy lokal agent qo'shiladi (`docs/PLAN.md`
dagi roadmap).
