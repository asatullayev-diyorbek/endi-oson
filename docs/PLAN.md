# "Endi Oson" — Lokal fayl uzatish + Telegram login: Implementatsiya rejasi

## Kontekst

Loyiha — ikki qattiq talabga asoslangan fayl almashish xizmati:

1. **Fayl trafigi 100% lokal tarmoq ichida** uzatiladi (server/Telegram/TURN orqali o'tmaydi); lokal ulanish bo'lmasa, transfer boshlanmaydi.
2. **Autentifikatsiya Telegram orqali**: bir martalik, qisqa muddatli token asosida `/start TOKEN` deep-link flow.

Repo hozir bo'sh (birinchi commit hali yo'q) — bu greenfield loyiha. Foydalanuvchi bilan kelishilgan asosiy arxitektura qarori: **V1 — faqat brauzer (WebRTC host-only + getStats tekshiruvi) orqali "amaliy darajadagi" lokal kafolat**; haqiqiy qat'iy (OS darajasidagi interfeys/subnet tekshiruvchi) lokal agent — **keyingi bosqich sifatida roadmap'da**, V1'ni bloklamaydi. Bu cheklov (brauzer tarmoq interfeysini to'liq nazorat qila olmaydi) foydalanuvchiga UI'da ochiq ko'rsatiladi.

Ushbu hujjat — 7 bosqichli implementatsiya rejasi, har biri uchun aniq modullar, modellar, endpoint'lar va qabul qilish mezonlari bilan. Foydalanuvchining o'z tavsiyasiga ko'ra tartib: **avval Telegram login + akkauntlar, keyin qurilmalar, keyin lokal-only transport mezonlari, so'ng fayl uzatish.**

---

## 0-bosqich: Texnologik stack va loyihaviy skelet

**Backend:** Django 5.x + Django REST Framework (API uchun) + Django Channels (WebSocket — signaling va online holat uchun) + PostgreSQL + Redis (Channels layer + token/sessiya cache).
**Bot:** aiogram 3.x, alohida process (`manage.py runbot` yoki systemd service), Django ORM'ga to'g'ridan-to'g'ri async-safe kirish (`sync_to_async`) orqali ulanadi.
**Frontend:** Vanilla JS + Django shablonlari (hech qanday SPA framework shart emas — WebRTC va DataChannel kodi tabiatan vanilla JS bilan yoziladi; build step kerak emas, MVP tezroq chiqadi).
**Deploy:** Ubuntu + Nginx (TLS termination, reverse proxy) + Gunicorn/Daphne (ASGI, Channels uchun kerak) + systemd xizmatlari (web, bot, worker).
**Muhim:** Butun loyiha ASGI bo'lishi kerak (Channels WebSocket uchun), shuning uchun `daphne` yoki `uvicorn` ishlatiladi, WSGI emas.

### Repo tuzilishi

```
endi-oson/
├── manage.py
├── config/                      # Django settings, asgi.py, urls.py
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── asgi.py
│   └── urls.py
├── apps/
│   ├── accounts/                # Foydalanuvchi modeli, profil
│   │   ├── models.py            # User(AbstractBaseUser) — telegram_user_id bilan
│   │   └── services.py
│   ├── telegram_auth/           # Login flow
│   │   ├── models.py            # LoginAttempt
│   │   ├── bot.py                # aiogram handlers
│   │   ├── services.py          # token generate/verify, atomic consume
│   │   └── views.py              # create-attempt, poll-status, complete-login
│   ├── devices/                  # Onlayn qurilmalar ro'yxati
│   │   ├── models.py             # Device, DeviceSession
│   │   └── consumers.py          # Channels consumer — presence
│   ├── signaling/                 # WebRTC offer/answer/ICE almashish
│   │   └── consumers.py
│   └── transfers/                  # Ulanish rozilik + transfer metadata (log, fayl o'zi emas!)
│       ├── models.py              # ConnectionRequest, TransferLog
│       └── consumers.py
├── static/
│   └── js/
│       ├── webrtc.js              # Peer connection, local-only enforcement
│       ├── transfer.js            # DataChannel chunking, progress
│       └── signaling.js
├── templates/
├── .env.example
└── docker-compose.yml (dev uchun: postgres + redis)
```

### Asosiy modellar (umumiy ko'rinish)

```python
# apps/accounts/models.py
class User(AbstractBaseUser):
    telegram_user_id = models.BigIntegerField(unique=True, db_index=True)  # o'zgarmas ID — username emas
    telegram_username = models.CharField(max_length=64, null=True, blank=True)  # faqat ko'rsatish uchun
    display_name = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

# apps/telegram_auth/models.py
class LoginAttempt(models.Model):
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)  # sha256(token)
    browser_session_id = models.CharField(max_length=64, db_index=True)  # cookie bilan bog'langan anon id
    status = models.CharField(choices=[("pending","pending"),("confirmed","confirmed"),("expired","expired")], default="pending")
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()   # created_at + 5 daqiqa
    consumed_at = models.DateTimeField(null=True, blank=True)

# apps/devices/models.py
class Device(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices")
    device_label = models.CharField(max_length=128)  # "MacBook Pro", "iPhone 15" kabi
    channel_name = models.CharField(max_length=255, null=True)  # faol WS ulanish uchun
    last_seen = models.DateTimeField(auto_now=True)
    is_online = models.BooleanField(default=False)

# apps/transfers/models.py
class ConnectionRequest(models.Model):
    from_device = models.ForeignKey(Device, related_name="sent_requests", on_delete=models.CASCADE)
    to_device = models.ForeignKey(Device, related_name="received_requests", on_delete=models.CASCADE)
    status = models.CharField(choices=[("pending","pending"),("accepted","accepted"),("rejected","rejected"),("timeout","timeout")])
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

class TransferLog(models.Model):
    # DIQQAT: faqat metadata — fayl baytlari bu yerda HECH QACHON saqlanmaydi/oqib o'tmaydi
    connection = models.ForeignKey(ConnectionRequest, on_delete=models.CASCADE)
    file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    status = models.CharField(choices=[("in_progress","in_progress"),("completed","completed"),("failed","failed"),("rejected_non_local","rejected_non_local")])
    local_verified = models.BooleanField(default=False)  # getStats tekshiruvi natijasi
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
```

---

## 1-bosqich: Django foundation

- `config/settings/{base,dev,prod}.py`: `.env` orqali `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `TELEGRAM_BOT_TOKEN`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`.
- PostgreSQL + Redis `docker-compose.yml` (dev uchun).
- ASGI konfiguratsiyasi (`config/asgi.py`) — `ProtocolTypeRouter` bilan HTTP + WebSocket marshrutlari.
- Custom `User` modeli (`AUTH_USER_MODEL = "accounts.User"`) — loyihani boshida o'rnatish shart, keyin almashtirib bo'lmaydi.
- Nginx config shabloni: HTTPS (Let's Encrypt/certbot), `/ws/` ni Daphne'ga proxy qilish (`proxy_set_header Upgrade $http_upgrade`).
- **Qabul mezoni:** `manage.py runserver` / `daphne` lokal ishga tushadi, admin panel ochiladi, bo'sh WebSocket endpoint ulanishni qabul qiladi.

## 2-bosqich: Telegram login

**Oqim (foydalanuvchi tasvirlagani bilan bir xil):**

1. `POST /auth/telegram/start/` — Django `browser_session_id` cookie'ni o'rnatadi (agar yo'q bo'lsa), `secrets.token_urlsafe(32)` bilan token yaratadi (~43 belgi, URL-safe, 64 dan kam), `sha256(token)` ni `LoginAttempt.token_hash` ga saqlaydi (xom token bazada SAQLANMAYDI), `expires_at = now()+5min`. Javob: `{"deep_link": "https://t.me/BOT_USERNAME?start=<token>", "attempt_id": "..."}`.
2. Frontend foydalanuvchini shu deep-link'ga yo'naltiradi (yangi tab/redirect) va parallel ravishda `GET /auth/telegram/poll/<attempt_id>/` ni har 2 soniyada so'raydi (yoki WebSocket orqali push — Channels group `login.<attempt_id>`).
3. Bot `/start <token>` qabul qiladi (`apps/telegram_auth/bot.py`, aiogram handler). Bot **faqat** Telegram update'dan kelgan `message.from_user.id` (haqiqiy, soxtalashtirib bo'lmaydigan) ni oladi — hech qachon foydalanuvchi yuborgan matndan emas.
4. `TelegramAuthService.confirm(token, telegram_user_id)` — **atomik tranzaksiya**: `select_for_update()` bilan `LoginAttempt`ni hash orqali topadi, `status=="pending"` va `expires_at > now()` ekanini tekshiradi, `telegram_user_id` bo'yicha `User.objects.get_or_create()`, `status="confirmed"`, `consumed_at=now()` qo'yadi — bir tranzaksiyada, shu bilan bir token ikki marta ishlatilishi oldini oladi (race condition'ga qarshi `select_for_update` + unique constraint muhim).
5. Bot foydalanuvchiga "✅ Kirish tasdiqlandi" xabarini yuboradi.
6. Frontend poll/WS orqali `confirmed` holatini ko'radi → `POST /auth/telegram/complete/<attempt_id>/` ni chaqiradi (hali ham shu `browser_session_id` cookie bilan — bu tokenni o'g'irlab olingan bo'lsa ham boshqa brauzerdan ishlatib bo'lmasligini ta'minlaydi). Backend `browser_session_id` moslashini tekshiradi, **yangi Django sessiya** yaratadi (`login(request, user)`), `secure`, `httponly`, `samesite="Lax"` cookie o'rnatadi.
7. **Muhim cheklov:** token hech qachon tayyor sessiya cookie sifatida botdan brauzerga uzatilmaydi — bosqich 6 har doim saytning o'z HTTPS originida bajariladi.

**Xavfsizlik nazorat ro'yxati (shart):**
- Token: `secrets.token_urlsafe`, bazada faqat hash, bir martalik (`consumed_at` tekshiruvi + atomik `select_for_update`), 5 daqiqa TTL.
- Rate limit: `start/` endpoint IP bo'yicha cheklanadi (django-ratelimit yoki oddiy Redis counter) — token flooding'ga qarshi.
- `.env` orqali `TELEGRAM_BOT_TOKEN`, `SECRET_KEY` — hech qachon kodga yozilmaydi, `.gitignore`ga `.env` qo'shiladi.
- Webhook (agar polling emas, webhook tanlansa) — Telegram'ning `secret_token` header orqali tekshiriladi.

**Qabul mezoni:** real Telegram bot bilan to'liq oqim ishlaydi — yangi foydalanuvchi uchun akkaunt yaratiladi, mavjud `telegram_user_id` uchun qayta akkaunt yaratilmaydi, eskirgan/ishlatilgan token rad etiladi.

## 3-bosqich: Qurilmalar (Devices)

- Login qilingandan keyin frontend `navigator.userAgent` + foydalanuvchi kiritgan nom asosida `Device` yaratadi/yangilaydi (`POST /devices/register/`).
- Channels consumer (`DeviceConsumer`, `apps/devices/consumers.py`) — WS ulanganda `Device.is_online=True`, `channel_name` saqlanadi, `user.<id>` group'iga qo'shiladi; uzilganda (`disconnect`) offline qiladi.
- Bir foydalanuvchining barcha qurilmalari — real-time ro'yxat (WS push: `device.online`/`device.offline` event'lari group orqali).
- UI: "Mening qurilmalarim" sahifasi — onlayn/oflayn holat, qurilma nomini tahrirlash.

**Qabul mezoni:** ikki brauzer/qurilmadan bitta akkauntga kirilganda, ikkisi ham bir-birini real-time onlayn ro'yxatda ko'radi.

## 4-bosqich: Ulanish rozilik (Connection consent)

- `A` qurilmasi `B` qurilmasiga ulanish so'rovi yuboradi: `ConnectionRequest(status="pending")` + WS orqali `B`ga `connection.request` eventi push qilinadi.
- `B` UI'da "Qabul qilish / Rad etish" modal ko'radi, 30 soniya timeout (frontend taymer + backend `Celery`/oddiy signal orqali `timeout` holatiga o'tkazish — MVP uchun frontend taymer + backend endpoint yetarli, Celery shart emas).
- Qabul qilinsa → signaling bosqichi (5-bosqich) boshlanadi; rad etilsa/timeout → `A`ga tegishli WS eventi.

**Qabul mezoni:** so'rov yuborilgandan 30 soniya ichida javob bo'lmasa, so'rov avtomatik `timeout` bo'ladi va ikki tarafga ham bildiriladi.

## 5-bosqich: Lokal-only WebRTC (eng muhim va nozik bosqich)

### 5.1 — Signaling (server orqali, lekin fayl baytisiz)

`apps/signaling/consumers.py` — Channels consumer, faqat SDP offer/answer va ICE candidate JSON paketlarini `A`↔`B` orasida relay qiladi (bular kichik matn, fayl emas). Bu to'liq ruxsat etilgan — signaling internet orqali o'tishi **shart**, chunki boshqa yo'l bilan peer'lar bir-birini topa olmaydi; faqat **fayl baytlari** lokal bo'lishi kerak.

### 5.2 — WebRTC konfiguratsiyasi (frontend, `static/js/webrtc.js`)

```javascript
const peerConnection = new RTCPeerConnection({
  iceServers: [],              // STUN/TURN yo'q — relay orqali o'tish imkoniyati yo'qoladi
  iceTransportPolicy: "all"    // host-only'ni getStats() orqali qattiq tekshiramiz (pastda)
});
```

### 5.3 — Lokal tekshiruv (getStats + IP heuristika) — V1 "amaliy kafolat"

`connectionState === "connected"` bo'lgach:

1. `peerConnection.getStats()` dan **selected candidate pair**ni topish (`nominated: true` yoki `transport.selectedCandidatePairId` orqali).
2. Ikki tarafning candidate `type` maydoni — **faqat** `"host"` bo'lishi shart. `"srflx"`, `"prflx"`, `"relay"` — darhol rad etish.
3. Qo'shimcha heuristika: candidate IP'lari **private range**da ekanini tekshirish (`10.x`, `172.16-31.x`, `192.168.x`) — public IP chiqib qolsa (masalan VPN/noto'g'ri interfeys), rad etish.
4. (Ixtiyoriy, kuchaytirish uchun) ikki IP bir xil `/24` subnet'da ekanini solishtirish — turli xil lokal tarmoqlarda bo'lgan ikkita qurilmani (masalan ikki alohida ofis Wi-Fi'si, lekin ikkisi ham "private" IP) chiqarib tashlash uchun qo'shimcha signal, lekin bu yolg'iz yetarli emas (NAT orqasida bo'lsa ham public bo'lishi mumkin — shuning uchun host-only + private-range tekshiruvi asosiy mezon).
5. Shu tekshiruvlardan **birortasi** o'tmasa → DataChannel ochilmaydi, `peerConnection.close()`, UI'da aniq xatolik: *"Lokal ulanish o'rnatilmadi — fayl internet orqali yuborilmaydi."* `TransferLog.status="rejected_non_local"` yoziladi (audit uchun).
6. Ulanish davomida ham (`onconnectionstatechange` / periodik `getStats()` poll, masalan har 3 soniyada) — agar candidate pair o'zgarib relay/srflx'ga o'tsa (ICE restart holati), transfer **darhol** to'xtatiladi.

### 5.4 — Ochiq cheklov (foydalanuvchiga ko'rsatiladi)

README/UI'da aniq yoziladi: *"Brauzer tomonidan amalga oshiriladigan bu tekshiruv amaliy darajada ishonchli, lekin OS tarmoq interfeysini to'liq dasturiy nazorat qilish brauzer xavfsizlik modeli tufayli imkonsiz. Qat'iy (OS darajasidagi) kafolat kerak bo'lgan hollar uchun kelajakda ixtiyoriy lokal agent qo'shiladi (roadmap, 8-bosqich)."*

**Qabul mezoni:** bir xil Wi-Fi'dagi ikki qurilma orasida DataChannel ochiladi; A qurilmasi mobil internetga (boshqa tarmoq) o'tkazilganda — ulanish rad etiladi va aniq xatolik ko'rsatiladi; `getStats()` log'da selected pair har doim `host`/`host` ekani tasdiqlanadi.

## 6-bosqich: Fayl almashish

- `static/js/transfer.js`: faylni `File.slice()` bilan bo'laklarga bo'lish (masalan 16KB-64KB chunk, DataChannel `bufferedAmountLowThreshold` bilan backpressure nazorati — xotira portlashining oldini olish uchun).
- Metadata frame (JSON: `{name, size, mimeType, totalChunks}`) birinchi bo'lib yuboriladi, keyin binary chunk'lar ketma-ket.
- Qabul qiluvchi tomon: `ReadableStream`/`Blob` yig'ish, progress bar (`received/total`), yakunda SHA-256 checksum solishtirish (yaxlitlik tekshiruvi — ixtiyoriy, lekin tavsiya etiladi).
- Bekor qilish: har ikki tarafdan `cancel` control-message, DataChannel yopiladi, qisman fayl frontendda tashlab yuboriladi.
- **Server bu bosqichda umuman ishtirok etmaydi** — faqat `TransferLog` orqali boshlanish/tugash/status fakti yoziladi (fayl nomi, hajmi — baytlar emas).

**Qabul mezoni:** 500MB+ fayl ikki qurilma orasida xatosiz, progress bilan uzatiladi; tarmoq uzilganda transfer to'xtaydi va resume/qayta urinish emas, aniq xatolik beriladi (MVP — resume keyingi iteratsiya).

## 7-bosqich: Xavfsizlik va test

- **Tarmoqlararo test:** ikki qurilmani qasddan turli tarmoqlarga (masalan, biri Wi-Fi, biri mobil hotspot) qo'yib, transfer **rad etilishini** tasdiqlash — bu eng kritik qabul testi.
- Server trafigini `tcpdump`/Wireshark bilan kuzatish — fayl baytlari serverga yetib bormasligini isbotlash (signaling trafigi — faqat kichik JSON — kutilgan).
- Token/sessiya xavfsizligi: eskirgan token, qayta ishlatilgan token, boshqa `browser_session_id`dan `complete` chaqirish — barchasi rad etilishini test qilish.
- Load/race test: bir token bilan parallel ikki `confirm` so'rovi yuborib, faqat bittasi muvaffaqiyatli bo'lishini tasdiqlash (atomiklik testi).
- `pytest-django` + `pytest-asyncio` (Channels consumer testlari uchun `channels.testing.WebsocketCommunicator`).

---

## Roadmap (V1'dan keyin, hozir ishlanmaydi)

- **8-bosqich:** Ixtiyoriy lokal agent (masalan, Tauri yoki kichik Go binary) — tarmoq interfeysi/subnet'ni OS darajasida tekshiradi va haqiqiy qat'iy lokal kafolat beradi; brauzer fallback sifatida qoladi.
- Fayl transferida resume/qayta ulanish.
- Ko'p faylni parallel yuborish, papka yuborish (zip-on-the-fly).

---

## Keyingi qadam

Reja tasdiqlangandan so'ng tavsiya etilgan ketma-ketlik: **0-bosqich (skelet) → 1-bosqich (Django foundation) → 2-bosqich (Telegram login)** birinchi commit/push sifatida amalga oshiriladi, so'ng foydalanuvchi bilan tekshirib, 3–7 bosqichlarga o'tiladi (har safar alohida PR/commit, kichik va tekshiriladigan qadamlar bilan).
