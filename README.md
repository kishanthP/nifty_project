# NIFTY 50 Alerts — Indian share market app

A live **NIFTY 50** dashboard with **price alerts**. You set a price and get a push
notification when NIFTY reaches it.

> Example: NIFTY is at **22,550**. Set **22,560** and the app knows you mean "notify me when
> it goes **above** 22,560". Set **22,540** and it's "notify me when it goes **below** 22,540".

Two kinds of alert (switch at the top of the form):
- **One price**: one target. Above or below is picked automatically from the current price.
- **High & low**: set both at once, e.g. **above 22,560 and below 22,540**, and get notified when either is hit.
  The form pre-fills prices 10 points either side of the live price. Optional checkbox **"Stop the other alert when one is hit"**:
  - **Off (default):** both sides stay active, so you can hear about the high and later about the low.
  - **On:** you hear only about the first breakout. The other side is stopped automatically, in the same
    database transaction, and the notification tells you so.

| Part | Technology | Why |
|---|---|---|
| Frontend | React 19 + TypeScript + Vite + Tailwind | Fast, typed, modern |
| Backend | FastAPI (Python 3.12) | Async, fast, auto API docs |
| Database | **PostgreSQL 16** | Reliable, relational, atomic updates (an alert can never fire twice) |
| Cache / live channel | **Redis 7** | Latest price in memory, pushes ticks to every API server |
| Market data | **Angel One SmartAPI** (free, real-time) | Official NSE feed, automatic daily login with TOTP |
| Login | Firebase Auth (Google sign-in, free) | No passwords to store |
| Notifications | Firebase Cloud Messaging (free, unlimited) | Browser push now, mobile app later |

---

## How it works (simple version)

```
Angel One ──ticks──► Market Worker ──► Redis (latest price + live channel)
                          │                     │
                          ▼                     ▼
                    Alert Engine         FastAPI (REST + WebSocket) ◄──► React app
                          │                     │
                          ▼                     ▼
                  Firebase (FCM) push     PostgreSQL (users, alerts, history)
```

1. **Market Worker** (`backend/app/workers/market_worker.py`) is a background program. It logs in to
   Angel One, receives every NIFTY price tick and saves the latest price in Redis.
2. On every tick the **Alert Engine** (`backend/app/services/alert_engine.py`) checks whether any alert's
   condition is now true. If it is, the alert is marked "triggered" and a push notification is sent.
3. **FastAPI** gives the React app what it needs: login, the live price (WebSocket) and your alerts.
4. **PostgreSQL** keeps permanent data. **Redis** is fast memory shared between the worker and the API.

### Why PostgreSQL (and Redis)?
- Your data is **relational** (users → alerts → notifications). PostgreSQL handles that well.
- Triggering is **one atomic SQL statement**, so even with several workers an alert fires only once.
- **Redis** is added alongside it, not instead of it. Live prices change every second, so they live in memory.
- **Later:** for price history, add the **TimescaleDB** extension to the same PostgreSQL. You won't need a new database.

### Reliability features
- The worker **reconnects automatically**, logs in to Angel One again every morning (08:30 IST),
  and logs in again whenever the session expires.
- **Only one worker** talks to the broker, enforced by a Redis lock. Start a second one and it waits on standby,
  then takes over automatically if the first dies.
- Notifications are saved **in the same transaction** as the trigger (the "outbox" pattern). If the worker
  crashes mid-send, the retry loop sends it later. Temporary FCM errors are retried 3 times.
- A quick spike that touches your price and comes back is **not missed**: the engine remembers the
  high and low prices between checks.
- Optional **fallback provider**: if Angel One goes quiet during market hours, Yahoo prices are used until it recovers.
- `GET /api/v1/health` reports database, Redis and live-feed status.

---

## Quick start (about 5 minutes, no accounts needed)

You need **Docker Desktop** running.

```bash
# 1. Create your config file from the template (first time only)
copy .env.example .env

# 2. Start everything
docker compose up --build
```

Then open **http://localhost:5174**. Port 5174 is used so this app can run next to another
Vite app on the default 5173. The default `.env` uses:
- `MARKET_DATA_PROVIDER=mock`: fake prices that move every second, so you can test alerts at any time.
- `AUTH_DEV_MODE=true`: a "Dev login" with just an email, so you can try it before setting up Firebase.

Try it: log in with any email and create an alert 5–10 points above the current price. Watch it trigger.
A toast appears in the app and the alert moves to the "Triggered" tab.

Other useful URLs (8000 is the default `API_PORT`; use your value if you changed it):
- API docs (try every endpoint): **http://localhost:8000/docs**
- Health: **http://localhost:8000/api/v1/health**

---

## Step 1: Real NIFTY prices from Angel One

You need four values. Never paste them into chats or screenshots.

| `.env` setting | What it is | Where to get it |
|---|---|---|
| `ANGELONE_CLIENT_CODE` | Your Angel One client ID, e.g. `A123456` | Angel One app → Profile |
| `ANGELONE_PIN` | Your **4-digit MPIN** (the PIN that opens the app), **not** your password | You set it in the app |
| `ANGELONE_API_KEY` | The API key of your SmartAPI app | Step 1 below |
| `ANGELONE_TOTP_SECRET` | The **secret key text** shown with the TOTP QR code (letters and digits, about 32 long), **not** the 6-digit code | Step 2 below |

1. **API key:** go to **https://smartapi.angelone.in**, sign up or log in with your client ID, then
   **My Apps → Create App**. Any app name works. Choose the market-data type ("Market Feeds") if offered,
   and use `https://localhost` as the redirect URL. Leave the static IP empty if the form allows that.
   Copy the **API key**. You don't need the secret key.
2. **TOTP secret:** on the SmartAPI site, open **Enable TOTP** (under your profile, or
   https://smartapi.angelone.in/enable-totp). Enter your client ID and MPIN, then the OTP sent to your
   phone or email. A QR code appears.
   - Copy the **text key shown with the QR code**. That is `ANGELONE_TOTP_SECRET`.
   - Also scan the QR code with Google Authenticator. Then you can still log in yourself.
3. Fill in the four values in `.env`, with no quotes and no spaces around `=`. Leave
   `MARKET_DATA_PROVIDER=mock` for now.
4. **Test them.** This works any time, including weekends:
   ```
   docker compose run --rm --no-deps api python -m app.tools.check_angelone
   ```
   It makes exactly **one** login attempt, then fetches the NIFTY 50 price, chart data and the live feed.
   It never prints your secrets. If something is wrong, it says which value to fix.
5. When the check says **All good**, switch the app over in `.env`:
   ```
   MARKET_DATA_PROVIDER=angelone
   FALLBACK_PROVIDER=yahoo      # optional safety net if Angel One goes quiet
   ```
   Apply it with `docker compose up -d`. (`docker compose restart` does **not** re-read `.env`.)
   Watch the worker with `docker compose logs -f worker`. You should see `Logged in to Angel One`.

Notes:
- Live ticks flow **09:15–15:30 IST on trading days**. Outside those hours you see the last price.
- If Angel One refuses the login, the worker tries **once more** a minute later, then **stops trying**.
  Repeated wrong logins could get your account blocked. Fix `.env` and run `docker compose up -d` to try again.
- The app only reads prices and never places orders. Angel One's static-IP rule is for placing orders.
- Keep `.env` private. Your MPIN and TOTP secret can log in to your account. `.env` is git-ignored.

## Step 2: Google login and push notifications (Firebase, free)

1. Go to **https://console.firebase.google.com** and **create a project**.
2. **Project settings → General → Your apps → Add app → Web.** Copy the config values into `.env`:
   `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`,
   `VITE_FIREBASE_STORAGE_BUCKET`, `VITE_FIREBASE_MESSAGING_SENDER_ID`, `VITE_FIREBASE_APP_ID`.
3. **Build → Authentication → Get started → Sign-in method → Google → Enable.**
4. **Project settings → Cloud Messaging → Web Push certificates → Generate key pair.** Copy the key into
   `VITE_FIREBASE_VAPID_KEY`.
5. **Project settings → Service accounts → Generate new private key.** Save the file as
   `backend/secrets/firebase-service-account.json`. It's a secret and is git-ignored.
6. In `.env` set `AUTH_DEV_MODE=false` and `VITE_AUTH_DEV_MODE=false`.
7. `docker compose up --build` again. Sign in with Google, then click **Enable notifications** in the top bar.
   Use **Notifications on → Send test notification** to check it works.

Push notifications work in Chrome, Edge and Firefox (desktop and Android). On iPhone, first add the site to the
Home Screen (iOS 16.4+).

---

## Project structure

```
share_market/
├── docker-compose.yml          Postgres, Redis, API, worker, frontend
├── .env.example                All settings (copy to .env)
├── backend/
│   ├── app/
│   │   ├── main.py             FastAPI app
│   │   ├── core/               settings, login check, Firebase
│   │   ├── db/ models/         database connection and tables
│   │   ├── schemas/            request/response shapes
│   │   ├── api/v1/             endpoints: market, alerts, devices, health, WebSocket
│   │   ├── services/
│   │   │   ├── market_data/    angelone.py, yahoo.py, mock.py (swappable providers)
│   │   │   ├── alert_engine.py checks prices against alerts
│   │   │   ├── notifier/       Firebase push
│   │   │   └── market_hours.py NSE hours + holidays (data/nse_holidays.json)
│   │   └── workers/market_worker.py
│   ├── alembic/                database migrations
│   └── tests/
└── frontend/
    ├── public/firebase-messaging-sw.js   shows notifications when the tab is closed
    └── src/
        ├── pages/              Login, Dashboard
        ├── components/         price card, chart, alert form, alert list, ...
        ├── hooks/              live feed (WebSocket), queries, push notifications
        └── lib/                API client, formatting, alert rules
```

### Database tables
| Table | What it stores |
|---|---|
| `users` | One row per Google account |
| `instruments` | What we track (NIFTY 50 now; add rows for more) |
| `alerts` | Your alerts: above/below, target price, status (active / triggered / cancelled). The two sides of a High & low alert share a `group_id` |
| `device_tokens` | Browsers that can receive push notifications |
| `notifications` | Every notification sent, with status, for history and retries |

### API overview (`/api/v1`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/market/quote/NIFTY50` | Latest price |
| GET | `/market/candles/NIFTY50` | 1-minute candles for the chart |
| GET | `/market/status` | Is NSE open? Next open time |
| WS | `/ws/market` | Live prices, plus your alert events after you send `{"type":"auth","token":"..."}` |
| GET/POST | `/alerts` | List / create alerts (`condition` is optional; it's picked automatically) |
| POST | `/alerts/range` | High & low: `{"high_price": 22560, "low_price": 22540, "one_cancels_other": false}` creates both |
| PATCH/DELETE | `/alerts/{id}` | Edit, re-arm (`{"status":"active"}`) or delete |
| POST | `/devices`, `/devices/unregister`, `/devices/test` | Push notification devices |
| GET | `/me`, `/notifications`, `/health` | Profile, notification history, health |

---

## Adding more later (how it scales)

- **More indices or stocks:** add a row to `instruments`, then restart the worker. Example for BANKNIFTY:
  ```sql
  INSERT INTO instruments (symbol, name, exchange, instrument_type, angelone_exchange_type, angelone_token, yahoo_symbol)
  VALUES ('BANKNIFTY', 'NIFTY BANK', 'NSE', 'INDEX', 1, '99926009', '^NSEBANK');
  ```
  (Find Angel One tokens in their instrument list, `OpenAPIScripMaster.json`.)
- **Another broker** (Upstox, Zerodha): write one file in `services/market_data/` with `stream()` and
  `fetch_intraday()`, then register it in `factory.py`.
- **More notification channels** (Telegram, email): add a class next to `notifier/fcm.py`.
- **More users / traffic:** the API keeps no state of its own, so run more copies behind a load balancer. Redis delivers
  live prices to all of them. Keep one worker (plus an optional standby).
- **Database changes:** edit a model, then run
  `docker compose run --rm api alembic revision --autogenerate -m "describe change"` and
  `docker compose run --rm api alembic upgrade head`.

---

## Running tests

```bash
docker compose run --rm api pytest          # backend: alert engine, API, WebSocket, migrations
cd frontend && npm test                     # frontend: alert rules and formatting
```

## Running without Docker (optional)

Run only Postgres and Redis in Docker (`docker compose up postgres redis`), then:
- In `.env`, change `@postgres:` to `@localhost:` and `redis://redis` to `redis://localhost`.
- Backend: `cd backend`, `python -m venv .venv`, activate it, `pip install -r requirements.txt -r requirements-dev.txt`,
  `alembic upgrade head`, `uvicorn app.main:app --reload`. In a second terminal: `python -m app.workers.market_worker`.
- Frontend: `cd frontend`, `npm install`, `npm run dev`.

## Troubleshooting

| Problem | Fix |
|---|---|
| "No price yet" on the dashboard | Check the worker: `docker compose logs -f worker` |
| Worker says "Angel One refused the login" | Run the check command in Step 1. It names the value to fix. |
| `AB1050` (invalid TOTP) | `ANGELONE_TOTP_SECRET` must be the long key text, not the 6-digit code. If the key is right, the clock is off: quit and restart Docker Desktop. |
| `AB7001` | Put your 4-digit **MPIN** in `ANGELONE_PIN`, not your trading password |
| Worker says "Login stopped after 2 refused attempts" | On purpose, to protect your account. Fix `.env`, run the check, then `docker compose up -d` |
| Price not moving | Normal outside 09:15–15:30 IST, on weekends and on NSE holidays (`backend/app/data/nse_holidays.json`) |
| "Push not set up" in the top bar | Fill all `VITE_FIREBASE_*` values and `VITE_FIREBASE_VAPID_KEY`, then rebuild |
| Notifications show "logged only" | The backend can't find `backend/secrets/firebase-service-account.json` |
| Code changes not picked up on Windows | Already handled with polling. Restart the container if needed. |
| `Bind for 0.0.0.0:8000 failed: port is already allocated` | Another app uses port 8000. In `.env` set `API_PORT=8001` and `VITE_API_URL=http://localhost:8001`, then `docker compose up -d` |
| Docker Desktop stuck on "Starting the Docker Engine…" or crashes with "The file cannot be accessed by the system" | Update Docker Desktop (Update button in its window). A leftover `...\Docker\run\dockerInference` file can block startup on newer Windows builds: quit Docker and rename the `run` folder |

## Going to production (checklist)
- `ENVIRONMENT=production`, `AUTH_DEV_MODE=false`, strong `POSTGRES_PASSWORD`, real `CORS_ORIGINS` / `FRONTEND_URL`.
- Serve over **HTTPS**. Browsers only allow push notifications on HTTPS (localhost is the exception).
- Build the frontend (`npm run build`) and serve `frontend/dist` from a CDN or Nginx.
- Run the API with several workers (`uvicorn ... --workers 4`) and the market worker as one process.
- Use a managed PostgreSQL and Redis with backups.
- Update `nse_holidays.json` each December from the NSE circular.

> Prices are for information only. This is not investment advice.
