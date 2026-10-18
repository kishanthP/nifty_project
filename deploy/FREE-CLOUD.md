# Deploy for free, no card needed: Supabase + Render + Vercel

```
Your phone / PC ─► Vercel (React app)          https://YOUR-APP.vercel.app
                      │ API calls + live prices
                      ▼
                   Render (FastAPI + price worker)  https://nifty-api-xxxx.onrender.com
                      ├─► Render Key Value (Redis)
                      └─► Supabase (PostgreSQL)
UptimeRobot pings Render every 5 minutes so the free service never falls asleep.
```

| Service | What it runs | Free plan |
|---|---|---|
| **Supabase** | Database (users, alerts, notifications) | 500 MB, no card |
| **Render** | API + Angel One price feed + alert engine, and a small Redis | 1 web service, 512 MB RAM, no card |
| **Vercel** | The website | Hobby plan, no card |
| **UptimeRobot** | Keeps Render awake | 50 monitors, no card |

Sign in to all four with **GitHub**. It takes about 30–40 minutes.
Keep your local `.env` open: you'll copy values from it.

> **Order matters:** Supabase → Render → Vercel → back to Render → Firebase → UptimeRobot.

---

## 1. Supabase (database)

1. Go to https://supabase.com → **Start your project** → **Continue with GitHub**.
2. **New project:**
   - **Name:** `nifty-alerts`
   - **Database password:** click **Generate a password**, then **copy it somewhere safe**.
     If it contains `@ : / # ?`, generate again or make one with letters and digits only.
     Those characters break the connection address.
   - **Region:** **Southeast Asia (Singapore)**, next to Render's Singapore servers.
   - **Security options:** if you see **"Enable Data API"**, **turn it off**. This app doesn't use it,
     and leaving it on would make your tables reachable through Supabase's public API.
3. Click **Create new project** and wait about 2 minutes.
4. If you didn't see the Data API option: **Project Settings → Data API** → turn it **off**.
5. Click **Connect** (top of the page) → **Connection String** tab → choose **Session pooler**.
   Copy the address. It looks like this:
   ```
   postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
   ```
   Replace `[YOUR-PASSWORD]` (including the brackets) with your database password.
   This is your **DATABASE_URL**. Keep it private.

   Use **Session pooler** (port **5432**). Not *Direct connection*: Render can't reach it.
   Not *Transaction pooler*: port 6543 doesn't work with this app.

The app creates its tables by itself on first start.

## 2. Render (backend)

1. Go to https://render.com → **Get Started** → **GitHub**.
2. **New + → Blueprint** → connect GitHub and allow access to **nifty_project** → select it.
3. Render reads `render.yaml` and shows **nifty-api** (web service) and **nifty-redis** (Key Value).
   It asks for these values:

   | Key | What to enter |
   |---|---|
   | `DATABASE_URL` | The Supabase address from step 1.5 |
   | `FRONTEND_URL` | For now: `https://nifty-alerts.vercel.app`. You'll correct it in step 4. |
   | `CORS_ORIGINS` | The same as `FRONTEND_URL` |
   | `ANGELONE_API_KEY`, `ANGELONE_CLIENT_CODE`, `ANGELONE_PIN`, `ANGELONE_TOTP_SECRET` | Copy from your local `.env` |
   | `FIREBASE_CREDENTIALS_JSON` | Open `backend\secrets\firebase-service-account.json` in Notepad → **Ctrl+A**, **Ctrl+C** → paste the whole thing |

4. Click **Apply**. The first build takes about 5–8 minutes. Watch **nifty-api → Logs**. Good signs:
   ```
   Uvicorn running on http://0.0.0.0:10000
   Worker ... started: provider=failover notifier=fcm instruments=NIFTY50
   Logged in to Angel One as AA******61
   ```
5. Copy the service address at the top of the page, e.g. `https://nifty-api-ab12.onrender.com`.
   Open `https://nifty-api-ab12.onrender.com/api/v1/health`. It should say `"status":"ok"`.

> If Render asks for a card for the Blueprint, stop and tell me. Both services use free plans.

## 3. Vercel (website)

1. Go to https://vercel.com → **Sign Up** → **Hobby** → **Continue with GitHub**.
2. **Add New… → Project** → **Import** `nifty_project`.
3. **Project Name:** `nifty-alerts`. This becomes your address, e.g. `nifty-alerts.vercel.app`,
   or with a suffix if the name is taken.
4. **Root Directory → Edit → `frontend`**. The framework should show **Vite**.
5. **Environment Variables:** add these. You can paste several lines at once into the *Key* box.
   ```
   VITE_API_URL=https://nifty-api-ab12.onrender.com
   VITE_AUTH_DEV_MODE=false
   ```
   Then copy the seven `VITE_FIREBASE_...` lines from your local `.env`, including `VITE_FIREBASE_VAPID_KEY`.
   `VITE_API_URL` is your Render address from step 2.5, with no `/` at the end.
6. **Deploy**. After about 1–2 minutes you get your address, e.g. `https://nifty-alerts.vercel.app`.

## 4. Back to Render: allow the website

Render → **nifty-api → Environment** → edit both values to your **exact** Vercel address
(with `https://`, no `/` at the end):
```
FRONTEND_URL=https://nifty-alerts.vercel.app
CORS_ORIGINS=https://nifty-alerts.vercel.app
```
**Save Changes**. Render restarts the service by itself.

## 5. Firebase: allow Google login on Vercel

Firebase console → **Authentication → Settings → Authorized domains → Add domain** →
`nifty-alerts.vercel.app` (no `https://`) → **Add**.

## 6. UptimeRobot: keep Render awake

Render's free services fall asleep after 15 minutes without visitors. While asleep, there are
no prices and no alerts.
1. Go to https://uptimerobot.com → **Register for FREE**.
2. **+ New monitor** → type **HTTP(s)** →
   URL `https://nifty-api-ab12.onrender.com/api/v1/health/live` → interval **5 minutes** → **Create**.

UptimeRobot also emails you if the backend goes down.

## 7. Try it

1. Open your Vercel address → **Continue with Google**.
2. **Enable notifications** → allow → **Send test notification**.
3. On a trading day after 09:15 IST, the badge shows **Live**.

**Then switch your PC to mock data**, so only Render logs in to Angel One:
in your local `.env` set `MARKET_DATA_PROVIDER=mock`, then run `docker compose up -d`.

---

## Updating

Commit and `git push`. Render (backend changes) and Vercel (frontend changes) rebuild by themselves.

## Good to know

- **Free hours:** Render gives 750 free hours a month, and one service running all month uses about 744.
  **Don't create a second free Render web service**, or the hours run out before the month ends.
- **Short gaps:** Render sometimes restarts free services, and every deploy restarts it too.
  Prices pause for about a minute. Alerts still fire on the next price after that.
- **Redis** on the free plan isn't saved to disk. A restart only loses the cached latest price,
  which comes back within seconds.
- **Supabase** pauses free projects that are unused for a week. This app uses the database every day.
  If it ever pauses, click **Restore** in Supabase.
- **Secrets** live only in Render's and Vercel's settings, never in GitHub.

## Troubleshooting

| Problem | Fix |
|---|---|
| Render log: `password authentication failed` | Wrong password in `DATABASE_URL`, or the `[ ]` brackets were left in |
| Render log: `Tenant or user not found` | You copied the wrong address. Use **Session pooler**, whose user looks like `postgres.abcdefgh`. |
| Render log: `Network is unreachable` | You used *Direct connection*. Use **Session pooler**. |
| Render log: `Angel One refused the login` | Check the 4 `ANGELONE_` values in Render → Environment. The worker stops after 2 refused tries; saving the settings restarts it. |
| Render log: `FIREBASE_CREDENTIALS_JSON is not a valid service-account key` | Paste the **whole** JSON file again, from `{` to `}` |
| Website shows "Network error" / browser console says **CORS** | Step 4: `FRONTEND_URL` and `CORS_ORIGINS` must exactly match the Vercel address |
| Google login: "unauthorized domain" | Step 5 |
| Website loads slowly the first time in a while | Render was asleep. Check that the UptimeRobot monitor is running. |
| Page not found when refreshing `/login` | Vercel **Root Directory** must be `frontend`, so it uses `frontend/vercel.json` |
