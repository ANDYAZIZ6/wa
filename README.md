# WA Finance Bot

`WA Finance Bot` adalah aplikasi pencatatan keuangan via WhatsApp yang sudah dinaikkan dari demo menjadi baseline production untuk deployment mandiri.

## Yang Sudah Dikerjakan

- App factory dengan `development`, `testing`, dan `production` config
- Data layer berbasis SQLAlchemy dengan dukungan `SQLite` untuk local dev dan `PostgreSQL` untuk production
- Session hardening: cookie secure, lifetime, trusted host, `ProxyFix`
- CSRF protection untuk semua form web
- Validasi signature webhook Twilio
- Onboarding akun otomatis via chat WhatsApp, plus reset password aman
- Health endpoint: `GET /healthz` dan `GET /readyz`
- Server-side pagination untuk transaksi dan laporan
- Deploy path production via `gunicorn`, `Dockerfile`, dan `compose.yaml`
- Test otomatis dengan `pytest`

## Struktur

```text
wa_finance_bot/
  app/
    __init__.py
    auth.py
    config.py
    db.py
    main.py
    ops.py
    security.py
    whatsapp.py
    services/
      parser.py
      whatsapp_service.py
    utils.py
  templates/
  static/
  tests/
  .env.example
  .env.production.example
  compose.yaml
  Dockerfile
  gunicorn.conf.py
  requirements.txt
  requirements-dev.txt
  run.py
  wsgi.py
```

## Jalankan Local Development

```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
python run.py
```

URL utama:

- Login: [http://localhost:5000/login](http://localhost:5000/login)
- Dashboard: [http://localhost:5000/dashboard](http://localhost:5000/dashboard)
- Health: [http://localhost:5000/healthz](http://localhost:5000/healthz)

## Opsi Termudah Dan Gratis

Untuk testing WhatsApp paling cepat, gunakan `Twilio WhatsApp Sandbox` ditambah `Cloudflare Quick Tunnel`.

Kenapa jalur ini paling ringan:

- tidak perlu sender WhatsApp Business sendiri untuk mulai tes
- app ini sudah bisa menerima webhook Twilio dan membalas langsung
- bisa dijalankan dari laptop lokal

Langkah setup:

1. Buat akun Twilio dan aktifkan WhatsApp Sandbox
2. Ambil `join code` dari halaman sandbox Twilio
3. Expose app lokal ke internet:

```bash
cloudflared tunnel --url http://localhost:5000
```

4. Isi `.env`:

```bash
BASE_URL=https://subdomain-kamu.trycloudflare.com
TWILIO_AUTH_TOKEN=isi_auth_token_twilio
TWILIO_SANDBOX_ENABLED=true
TWILIO_SANDBOX_NUMBER=14155238886
TWILIO_SANDBOX_JOIN_CODE=isi_join_code_dari_twilio
TWILIO_SANDBOX_START_TEXT=halo
USE_PROXY_FIX=true
```

5. Di console Twilio Sandbox, set inbound webhook ke:

```text
https://subdomain-kamu.trycloudflare.com/webhooks/whatsapp
```

6. Restart app lalu buka `/login`
7. Klik `Gabung Sandbox WhatsApp`
8. Setelah WhatsApp membalas konfirmasi join, klik `Kirim "halo"` untuk memicu pembuatan akun otomatis

Catatan:

- Quick Tunnel gratis, tetapi hanya untuk testing/development
- Twilio Sandbox juga untuk testing, bukan jalur production final
- Untuk production final, ganti ke nomor bisnis sendiri dan domain tetap

## Jalankan Production Dengan Docker

1. Copy `.env.production.example` menjadi `.env.production`
2. Ganti `SECRET_KEY`, `DATABASE_URL`, `BASE_URL`, dan `TWILIO_AUTH_TOKEN`
3. Jalankan:

```bash
docker compose up --build -d
```

App akan listen di port `8000`.

## Onboarding User

Kirim request ke webhook:

```bash
curl -X POST http://localhost:5000/webhooks/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "6281234567890",
    "text": "halo",
    "message_id": "local-001",
    "provider": "local"
  }'
```

Balasan akan berisi `temporary_password`. User login ke web memakai nomor WhatsApp dan password sementara itu, lalu menggantinya di Settings.

## Flow "Buat Akun via WhatsApp"

Flow yang meniru CatatWA:

1. User buka halaman login
2. User klik tombol `Buat akun via WhatsApp`
3. Browser membuka `https://wa.me/<nomor-bot>?text=<pesan-awal>`
4. User menekan `Send` sekali di WhatsApp
5. Provider WhatsApp mengirim webhook inbound ke `POST /webhooks/whatsapp`
6. Backend membuat akun otomatis berdasarkan nomor pengirim, lalu membalas password sementara

Catatan penting:

- Website bisa membuka chat `wa.me`, tetapi tidak bisa mengirim pesan WhatsApp tanpa aksi user
- Untuk menampilkan tombol ini, isi `WHATSAPP_BOT_PHONE` dan `WHATSAPP_DEFAULT_TEXT`
- Untuk mode testing gratis via Twilio Sandbox, isi `TWILIO_SANDBOX_ENABLED=true` dan `TWILIO_SANDBOX_JOIN_CODE`

## Cloudflare Turnstile

Halaman login mendukung Cloudflare Turnstile seperti pola yang terlihat di situs CatatWA.

Isi env berikut untuk mengaktifkannya:

```bash
TURNSTILE_ENABLED=true
TURNSTILE_SITE_KEY=...
TURNSTILE_SECRET_KEY=...
TURNSTILE_EXPECTED_HOSTNAME=finance.example.com
```

Turnstile akan muncul di login dan token-nya divalidasi server-side sebelum proses autentikasi.

## Format Chat

- `10k jajan kopi`
- `-20k makan siang`
- `+3jt freelance`
- `500rb bonus`
- `saldo`
- `rekap`
- `mingguan`
- `bulanan`
- `saldo awal 500k`
- `lupa password`
- `reset saldo`
- `upgrade`

## Endpoint Utama

### Web

- `GET/POST /login`
- `GET /logout`
- `GET /dashboard`
- `GET/POST /transactions`
- `GET/POST /transactions/<id>/edit`
- `POST /transactions/<id>/delete`
- `GET /reports`
- `GET /reports/export.csv`
- `GET/POST /settings`

### Operational

- `GET /healthz`
- `GET /readyz`

### WhatsApp

- `POST /webhooks/whatsapp`
- `GET/POST /simulator` untuk development, nonaktif default di production

## Testing

```bash
pytest
```

## Catatan Production

- `APP_ENV=production` menolak `SQLite` agar deployment tidak jalan di storage lokal server
- JSON webhook lokal bisa dimatikan penuh lewat `ALLOW_JSON_WEBHOOKS=false`
- Simulator bisa dimatikan lewat `ENABLE_SIMULATOR=false`
- Login bisa diproteksi Turnstile dengan `TURNSTILE_ENABLED=true`
