# e-Dairy

A comprehensive digital platform that streamlines milk collection, quality tracking, and digital payments for dairy collection centres and farmers. Farmers can register with their mobile number, get linked to a collection centre, and track their milk supply, earnings, and payment requests — while collection centre operators manage collections, quality, payouts, and reports from a single dashboard.

## Features

### Authentication & Roles
- OTP-based registration and login using the mobile number as username (NepalOTP / Twilio / simulated mode).
- Two roles: **Farmer** and **Collection Centre Operator**.
- Automatic farmer code generation (`F1`, `F2`, ...) on farmer registration.

### Milk Collection & Quality
- Record morning/evening milk intake with quantity, FAT, and SNF.
- Automatic payout rate calculation: `rate = (FAT × 6) + (SNF × 4)`.
- Automatic amount calculation: `amount = quantity × rate`.
- Auto-created quality records synced with each collection.
- Filtering by date, session, and farmer.

### Farmer Linking & Management
- Collection centres can search farmers by code, name, or phone and link/unlink them.
- Deactivation is allowed only when the farmer's balance is fully settled; leftover pending payment requests are auto-resolved on deactivation.

### Payments & Payouts
- Disburse payments via **Cash**, **Bank Transfer**, or **Wallet** with optional deductions and transaction references.
- SMS alerts and in-app notifications sent to the farmer on each payout.
- Farmers can request payments from their linked collection centre.
- Farmer bank details management (up to 3 accounts, one primary) with QR codes.
- Real-time payout summaries and payment histories.

### Analytics & Reports
- Dashboard stats: total milk, average FAT/SNF, total earned, active farmers, weekly chart, recent records.
- Report builder: daily/monthly collection, quality, daily/monthly payments, and farmer-specific reports.

### Notifications & SMS
- In-app notification centre (payment requests, payment received, milk updates).
- SMS via Sparrow SMS for collections and payouts, with a local `sms_logs.txt` sandbox.

## Tech Stack

| Layer       | Technology                                                        |
|-------------|-------------------------------------------------------------------|
| Backend     | Django 6.0, Django REST Framework 3.17                            |
| Auth        | SimpleJWT (JWT Bearer tokens)                                     |
| Database    | MySQL (configurable via `.env`, SQLite also supported)            |
| SMS/OTP     | NepalOTP (primary), Twilio Verify (fallback), Sparrow SMS (notify)|
| Frontend    | Static HTML/CSS/JS served directly by Django                      |

## Project Structure

```
e-dairy/
├── backend/
│   ├── api/                    # Django app (models, views, serializers, urls)
│   │   ├── models.py           # Profile, DairyOperator, LinkedFarmer, MilkCollection,
│   │   │                       # Payment, QualityRecord, PaymentRequest, Notification...
│   │   ├── views.py            # All API endpoints
│   │   ├── serializers.py      # DRF serializers
│   │   ├── urls.py             # API URL routing (all under /api/)
│   │   └── twilio_helper.py    # OTP + SMS provider abstraction
│   ├── config/                 # Django project settings & root URLs
│   ├── manage.py
│   ├── requirements.txt
│   └── .env                    # Environment configuration
├── frontend/
│   ├── index.html              # Landing page
│   ├── login.html              # OTP login / registration
│   ├── collection_center-dashboard.html    # Collection centre dashboard
│   ├── farmer-dashboard.html   # Farmer dashboard
│   └── ...
├── e_dairy_api.postman_collection.json
└── README.md
```

## Prerequisites

- Python 3.10+
- MySQL server (or switch the `DB_ENGINE` env var to SQLite)
- SMS/OTP provider keys (optional — a simulated mode is built in)

## Setup

### 1. Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables (see below)
cp .env.example .env   # or create .env manually

# Apply migrations
python manage.py migrate

# Create a superuser (optional, for /admin/)
python manage.py createsuperuser

# Run the development server
python manage.py runserver
```

The frontend is served automatically by Django, so just open `http://127.0.0.1:8000/`. The API is available under `http://127.0.0.1:8000/api/`.

> Tip: A pre-populated `backend/db.sqlite3` is included for quick local demos. To use it, set `DB_ENGINE=django.db.backends.sqlite3` and `DB_NAME=db.sqlite3` (or simply remove `DB_ENGINE` and point `DB_NAME` to the file) in `.env`.

### 2. Environment Variables (`.env`)

Create a `.env` file in `backend/`:

```ini
# Django
SECRET_KEY=your-secret-key

# Database
DB_ENGINE=django.db.backends.mysql
DB_NAME=e_dairy
DB_USER=root
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=3306

# OTP / SMS (optional - falls back to simulation with code 123456)
NEPALOTP_API_KEY=notp_sandbox_xxxx   # primary OTP provider
TWILIO_ACCOUNT_SID=your-account-sid  # fallback OTP provider
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_VERIFY_SERVICE_SID=your-service-sid
TWILIO_DEFAULT_COUNTRY_CODE=+977
SPARROW_SMS_TOKEN=your-sparrow-token # payout/collection SMS
SPARROW_SMS_SENDER=EDairy
```

**Provider behaviour:**
- OTP is sent via **NepalOTP** when a valid key is present, otherwise **Twilio**, otherwise a simulated code `123456`.
- Payout/collection SMS use **Sparrow SMS**; when no token is configured, messages are written to `backend/sms_logs.txt` instead.

## Usage Flow

1. **Register/Login** → `login.html` requests an OTP to your mobile number, then creates the account or logs in (phone number = username).
2. **Collection centre** links farmers by their farmer code from `collection_center-dashboard.html`.
3. **Record milk intake** per session; the system computes rate & amount and notifies the farmer.
4. **Farmers** view earnings, add bank details, and request payments.
5. **Collection centre** reviews outstanding balances and disburses payouts (cash/bank/wallet).
6. Farmers who are fully settled can be deactivated/unlinked.

## API Overview

All endpoints are authenticated with a JWT Bearer token unless marked public. Base URL: `/api/`.

| Method | Endpoint                            | Description                                |
|--------|-------------------------------------|--------------------------------------------|
| POST   | `generate-code/`                    | Request OTP (purpose: `register`/`login`)  |
| POST   | `register/`                         | Create account (role: `farmer`/`agent`)    |
| POST   | `token/`                            | Login, returns access/refresh JWT          |
| POST   | `token/refresh/`                    | Refresh access token                       |
| GET    | `profile/`                          | Current user profile                       |
| GET    | `current_profile/`                  | Profile with dairy info                    |
| GET    | `farmers/`                          | List/search farmers                        |
| DELETE | `account/delete/`                   | Delete own account                         |
| GET    | `dashboard/`                        | Dashboard statistics                       |
| GET/POST| `collection/`                      | List/create milk collections (filters)     |
| GET/PUT/DELETE | `collection/<id>/`          | Collection detail/update/delete            |
| GET/POST| `quality/`                         | Quality records                            |
| GET/POST| `payments/`                        | Payments (role-scoped)                     |
| GET    | `dairy/dashboard/`                  | Collection centre summary                  |
| POST   | `dairy/link-farmer/`                | Link a farmer                              |
| POST   | `dairy/deactivate-farmer/`          | Unlink farmer (settled balance only)       |
| GET    | `dairy/linked-farmers/`             | Active linked farmers + balances           |
| GET    | `dairy/search-farmer/?farmer_code=` | Search farmer by code/name/phone           |
| POST   | `dairy/record-collection/`          | Record milk collection (SMS alert)         |
| GET    | `dairy/farmer-payable-summary/<id>/`| Farmer payout summary + bank info          |
| POST   | `dairy/process-payment/`            | Disburse payment (SMS + notification)      |
| GET    | `dairy/payment-history/<id>/`       | Payment history for a farmer               |
| POST   | `dairy/notify-pending-payment/`     | SMS reminder of pending balance            |
| GET    | `dairy/reports/`                    | Report builder                             |
| GET    | `farmer/payment-summary/`           | Farmer earnings/payments summary           |
| GET    | `farmer/collection-center-summary/` | Per-collection-centre balances             |
| GET/POST| `farmer/bank-details/`             | List/add bank accounts                     |
| PUT/DELETE| `farmer/bank-details/<id>/`      | Update/delete bank account                 |
| POST   | `farmer/request-payment/`           | Farmer requests a payment                  |
| GET    | `notifications/`                    | List notifications                         |
| POST   | `notifications/read-all/`           | Mark all notifications read                |
| POST   | `notifications/<id>/read/`          | Mark one notification read                 |

A full Postman collection is included at `e_dairy_api.postman_collection.json`.

## Notes

- In-app notifications are created only for payments with `payment_status = "paid"`.
- Disbursing a payment resolves the farmer's pending payment requests so links can be deactivated cleanly.
