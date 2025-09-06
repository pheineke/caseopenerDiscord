# Case Opener Simulator (Prototype)

A Flask prototype for a case opening simulator with user accounts, SQLite persistence, and a dark futuristic UI.

## Features
- User registration & login (session based, password hashing)  
- SQLite database via SQLAlchemy (auto-initialized with demo data)  
- User inventory with items (name, value, image, quantity)  
- Basic seed data (demo user only; items come solely from `scan_items.py`)  
- Themed UI (see `static/base.css`)  
 - Case selection & opening prototype (`/cases`, roulette animation, weighted rarity spin)  

## Data Model
`models.py` defines the structure:
- `User`: id, username (unique), password_hash, avatar, money, created_at
- `Item`: id, name (unique), value (int), image, created_at
- `InventoryItem`: id, user_id, item_id, quantity, created_at (acts as inventory association)

## Running
Create / activate a Python 3.10+ environment then install dependencies:

```bash
pip install -r requirements.txt
# optional: copy and edit env
cp .env.example .env
python app.py
```

Navigate to: http://127.0.0.1:8000/

Demo credentials (seeded):
- username: `johndoe`
- password: `password`

## Next Ideas
- Case definitions & opening logic w/ random drops
	- (Prototype implemented – move cases & odds to DB)
- Transactions & balance updates
- Rarity tiers & animations
- API endpoints for AJAX inventory updates
- CSRF protection & Flask-WTF forms

---
Prototype only: not production hardened (no rate limiting, CSRF, input validation rigor, etc.).


# TODOS
- (DONE) Add home page: shows balance, inventory total value, item count, and quick links.

- (DONE) Header nav with Home/Cases + avatar dropdown (profile, items, cases, logout).

## Running as a Discord Activity (Embedded App)

This app can run inside a Discord Activity iframe using the Discord Embedded App SDK.

1) Create a Discord Application in the Developer Portal and enable "Embedded App" (Activities).
2) Note the Application ID and Client Secret.
3) Run the app with these environment variables (add to .env or export):

Environment:
- DISCORD_ACTIVITY=1
- DISCORD_APP_ID=<your application id>
- DISCORD_CLIENT_SECRET=<your client secret>

The server sets cookies compatible with third‑party iframes (SameSite=None; Secure) and relaxes CSP for Discord domains. The client loads the SDK and performs an OAuth code flow via `/discord/exchange`.

## Docker

Build and run locally:

```bash
docker build -t caseopener .
docker run --rm -p 8000:8000 \
	--env-file .env \
	-v "$(pwd)/app.db:/app/app.db" \
	-v "$(pwd)/static/avatars:/app/static/avatars" \
	caseopener
```

Or with Compose:

```bash
docker compose up --build
```

Raspberry Pi (ARM) notes:
- The Dockerfile uses python:3.12-slim which has multi-arch manifests (arm/arm64/amd64). Building on a Pi should work out of the box.
- If building on x86 for ARM, use Buildx: `docker buildx build --platform linux/arm64,linux/amd64 -t yourrepo/caseopener .`
- Map the `app.db` and `static/avatars` volumes so data persists across container restarts.

### Cloudflare Tunnel (containerized)

You can run a Cloudflare Tunnel as a sidecar container using the provided compose file:

Ephemeral (quick) tunnel:
```bash
docker compose up --build
# Check the cloudflared container logs to get the https://*.trycloudflare.com URL
```

Named tunnel with a stable hostname:
```bash
# 1) Create a tunnel in your Cloudflare account and copy the token
# 2) Put it in your .env
echo CLOUDFLARE_TUNNEL_TOKEN=xxxxx >> .env
# 3) Bring services up
docker compose up -d --build
```

The app will be available via the tunnel’s HTTPS URL and on localhost:8000.

Notes:
- Only minimal identify scope is requested; link your in‑app account by adding a server endpoint to create/login users from the Discord user object (see `window.__discordUser`).
- Ensure you serve over HTTPS in production. Activities are https‑only.
