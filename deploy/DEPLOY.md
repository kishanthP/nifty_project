# Deploy for free: Oracle Cloud + DuckDNS

When you're done, the app runs 24/7 at `https://YOUR-NAME.duckdns.org`. That gives you live
Angel One prices, Google login and push notifications, even when your PC is off.

| Piece | Free service |
|---|---|
| Server | Oracle Cloud **Always Free** ARM server (Mumbai or Hyderabad) |
| Web address | **DuckDNS** subdomain |
| HTTPS certificate | **Caddy** + Let's Encrypt (automatic, renews by itself) |
| Code | Your GitHub repo |

It takes about 45 minutes the first time. In the commands below, replace:
- `niftyalerts.duckdns.org` → your DuckDNS address
- `SERVER_IP` → your server's public IP
- `C:\path\to\ssh-key.key` → where you saved the server's private key

---

## 1. Create the server (Oracle Cloud)

1. Sign in at https://cloud.oracle.com. Your **home region** must be **India West (Mumbai)**
   or **India South (Hyderabad)**.
2. **☰ Menu → Compute → Instances → Create instance.**
3. **Name:** `nifty-server`.
4. **Image and shape → Edit:**
   - **Image:** click *Change image* → **Canonical Ubuntu 24.04** (or 22.04).
   - **Shape:** click *Change shape* → **Ampere** → **VM.Standard.A1.Flex**,
     with **2 OCPUs and 12 GB memory**. That stays inside the free limit of 4 OCPUs and 24 GB.
     The page should show the **"Always Free-eligible"** label.
5. **Networking:** keep the defaults. Make sure **"Assign a public IPv4 address"** is on.
6. **Add SSH keys:** choose **Generate a key pair for me** → **Save private key**.
   Keep this file safe. It's the only way into your server.
7. Click **Create**. After 1–2 minutes the state turns **Running**. Copy the **Public IP address**.

> **"Out of capacity" error?** Free ARM servers are popular. Try again later (early morning
> works best), pick a different *availability domain*, or use 1 OCPU and 6 GB.

## 2. Open the web ports in Oracle

1. On the instance page, click the **subnet** link (under *Primary VNIC*), then **Security Lists →
   Default Security List**. In the newer console it may be under **Security → Security lists**.
2. **Add Ingress Rules**, twice:
   - Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination port **80**
   - Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination port **443**

## 3. Point your DuckDNS address at the server

1. Sign in at https://www.duckdns.org.
2. Next to your subdomain, type the **server's public IP** into *current ip* → **update ip**.

## 4. Allow the address in Firebase (for Google login)

Firebase console → **Authentication → Settings → Authorized domains → Add domain** →
`niftyalerts.duckdns.org` → **Add**.

## 5. (Optional) Angel One static IP

The server's IP doesn't change while the server exists. You can put it in your SmartAPI app
(**smartapi.angelone.in → My Apps → edit → Primary Static IP**). That isn't needed for prices,
but it is needed if you ever add order placement.

## 6. Make the server's settings file (on your PC)

In the project folder, in **Git Bash**:
```bash
bash deploy/make-production-env.sh niftyalerts.duckdns.org
```
This writes `.env.production`. It copies your Angel One and Firebase values from `.env`, adds
production settings, and creates a new random database password.
The file is git-ignored. Never share it.

## 7. Connect to the server and install everything

In **PowerShell** on your PC:

1. Let only you read the key file. SSH refuses keys that other users can read:
   ```powershell
   icacls "C:\path\to\ssh-key.key" /inheritance:r /grant:r "$($env:USERNAME):R"
   ```
2. Connect:
   ```powershell
   ssh -i "C:\path\to\ssh-key.key" ubuntu@SERVER_IP
   ```
   Type `yes` the first time. You are now *on the server*. The prompt shows `ubuntu@nifty-server`.
3. Get the code and set up the server:
   ```bash
   git clone https://github.com/kishanthP/nifty_project.git
   cd nifty_project
   bash deploy/setup-server.sh
   exit
   ```

Back on your PC (PowerShell, in the project folder), copy the two secret files to the server:
```powershell
scp -i "C:\path\to\ssh-key.key" .env.production ubuntu@SERVER_IP:nifty_project/.env
scp -i "C:\path\to\ssh-key.key" backend\secrets\firebase-service-account.json ubuntu@SERVER_IP:nifty_project/backend/secrets/
```

## 8. Start the app

```powershell
ssh -i "C:\path\to\ssh-key.key" ubuntu@SERVER_IP
```
```bash
cd nifty_project
docker compose -f docker-compose.prod.yml up -d --build
```
The first build takes about 5–10 minutes. Then check it:
```bash
docker compose -f docker-compose.prod.yml ps        # every service "running" / "healthy"
docker compose -f docker-compose.prod.yml logs worker --tail 20   # "Logged in to Angel One"
```
Open **https://niftyalerts.duckdns.org** → **Continue with Google** → **Enable notifications** →
**Send test notification**. Your browser keeps notification permission separately for each site,
so you have to allow it again here.

**Then switch your PC back to mock data**, so that only the server logs in to Angel One. In your
local `.env`, set `MARKET_DATA_PROVIDER=mock`, then run `docker compose up -d`.

---

## Updating after you change code

On your PC: commit and `git push`. Then on the server:
```bash
cd nifty_project
bash deploy/update.sh
```

## Changing a setting on the server

```bash
nano .env            # edit, then Ctrl+O, Enter, Ctrl+X
docker compose -f docker-compose.prod.yml up -d
```
If you changed a `VITE_...` value, add `--build`. Those values are built into the web app.

## Backups

The `backup` service saves the database every 24 hours into `nifty_project/backups/` and keeps
the newest 14. To copy them to your PC now and then (PowerShell):
```powershell
scp -i "C:\path\to\ssh-key.key" -r ubuntu@SERVER_IP:nifty_project/backups .\server-backups
```
To restore a backup on the server. This **replaces** the current data:
```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' \
  < backups/share_market-YYYY-MM-DD_HHMM.dump
```

## Useful commands (on the server, in `nifty_project`)

| What | Command |
|---|---|
| Status | `docker compose -f docker-compose.prod.yml ps` |
| Live logs | `docker compose -f docker-compose.prod.yml logs -f worker api` |
| Restart everything | `docker compose -f docker-compose.prod.yml restart` |
| Check Angel One login | `docker compose -f docker-compose.prod.yml run --rm --no-deps api python -m app.tools.check_angelone` |
| Health | `curl -s https://niftyalerts.duckdns.org/api/v1/health` |

## Troubleshooting

| Problem | Fix |
|---|---|
| Site doesn't open at all | Check step 2 (Oracle ingress rules) and that `setup-server.sh` ran. Check that DuckDNS shows the server IP. |
| Browser warns about the certificate | Caddy couldn't get a certificate yet. It needs ports 80 and 443 open and DuckDNS pointing at the server. See `docker compose -f docker-compose.prod.yml logs web`. |
| Google login says "unauthorized domain" | Step 4: add the DuckDNS address in Firebase. |
| `Permission denied (publickey)` | Use the key from step 1 and the user `ubuntu`. |
| `UNPROTECTED PRIVATE KEY FILE` | Run the `icacls` command from step 7. |
| `permission denied ... docker.sock` | Log out and in again after `setup-server.sh`. |
| Worker: "Angel One refused the login" | Run the check command above. If you changed your MPIN, update `.env` on the server. |
| Oracle stopped the server ("idle") | Oracle can reclaim Always Free servers that sit nearly idle for 7 days. Upgrading the account to *Pay As You Go* stops this, and Always Free resources stay free. |
