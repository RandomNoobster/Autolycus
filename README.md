# About Autolycus

Autolycus is an open source bot for finding raid targets in PnW. It was initially developed for in-house usage, but I decided to make it public. As far as I am aware, no other public bots have extensive raid finding functionality. The lack of such functionality is what motivated me to make this public. Nonetheless, the fact that it was originally meant for in-house usage means multiple things. Firstly, it means that the code isn't pretty. Secondly, it means that it's not designed to be easy to self-host. 

## Repository organization

The codebase uses a layered structure:

- `api/` - Flask delivery layer (HTTP routes, auth/security, request handling)
- `bot/` - Discord process (`cogs/`, `discord_utils/`, `attachments/`; run with `uv run bot` or `python -m bot`)
- `services/` - shared application orchestration (feature flows reused by API + bot)
- `logic/` - domain/business logic (calculations and pure game rules)
- `database/` - data-access modules (Mongo + SQLite cache access)
- `infra/` - cross-cutting infrastructure (cache implementation)
- `core/` - shared runtime configuration
- `frontend/` - React/Vite web client
- `scanner.py` - worker process that hydrates local SQLite cache data

### Import rules

- `logic` must not import from `api`.
- `api` and `bot` can import from `services`, `logic`, `database`, `infra`, and `core`.
- New SQLite cache imports should use `database.sqlite_cache`.
- New cache imports should use `infra.cache`.
- New config imports should use `core.config`.

Compatibility re-export modules still exist for now (`api/cache.py`, `api/config.py`, `utils/db_utils.py`) to avoid breakage during migration, but new code should avoid them.

## Local development with uv (non-Docker)

This repository now supports `uv` as the primary Python workflow.

### 1) Install dependencies

From the repository root:

```bash
uv sync
```

This installs dependencies for API, scanner, and Discord bot in one environment.

### 2) Run services

Use separate terminals:

```bash
# API (http://localhost:5000)
uv run api
```

```bash
# API with hot reload (watch Python file changes)
uv run watchfiles --filter python "uv run api" api logic database core infra services bot
```

```bash
# Discord bot
uv run bot
```

```bash
# Scanner worker
uv run python scanner.py
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

### 3) Environment variables

Create a `.env` file at repository root with at least:

- `api_key` (Politics & War API key)
- `bot_token` (Discord bot token)
- `debug_channel` (Discord channel ID for bot logging)
- `pymongolink` (MongoDB connection URI)
- `databaselink` (main MongoDB URI — often the same as `pymongolink`)
- `version` (MongoDB database name)
- `SECRET_KEY` (recommended for stable auth tokens across restarts)

Optional but needed for some features:

- `bot_key` — PnW **bot** key (separate from `api_key`); used for game API calls in builds/market/damage flows
- `DISCORD_BOT_API_KEY` — shared secret the bot sends as `X-Bot-Token` to the API (e.g. `/api/auth/token/issue`); must match in API and bot `.env`
- `AUTH_TOKEN_API_KEY` — shared secret for `POST /api/auth/token/generate` if you use that flow from the web app

## Production Docker deployment (Oracle Linux)

This project ships with a production-ready Docker setup that runs:

- Flask API (Waitress)
- Discord bot
- Scanner worker
- Frontend (Nginx + Vite build)

It also includes a systemd timer that regularly pulls the repo, rebuilds images,
and restarts services, so the stack stays up-to-date and resilient on crashes.

### Recommended TLS setup (Caddy + domain)

Use a real domain and terminate HTTPS in Caddy. Keep API traffic inside Docker.

- Public ingress: only `80/443` on the VM.
- Internal service calls: `bot -> http://api:5000`.
- Do not expose API port `5000` publicly.

Additional `.env` values for Caddy:

```
SITE_DOMAIN=autolycus.your-domain.com
ACME_EMAIL=you@your-domain.com
```

Production URL values:

```
# Public URL users click in Discord
AUTOLYCUS_WEB_BASE_URL=https://autolycus.your-domain.com

# Internal Docker URL for bot -> API calls
AUTOLYCUS_API_BASE_URL=http://api:5000
```

### 1) Prerequisites (Oracle Linux)

Install Docker Engine and the Compose plugin. Example for Oracle Linux 8/9:

```
sudo dnf -y install dnf-utils
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
```

Ensure your user can run Docker:

```
sudo usermod -aG docker $USER
```

Log out and back in to refresh group membership.

### 2) Clone the repository

These systemd files assume the repo lives at `/opt/autolycus`.

```
sudo mkdir -p /opt/autolycus
sudo chown $USER:$USER /opt/autolycus
git clone <your-fork-url> /opt/autolycus
cd /opt/autolycus
```

If you choose a different path, update the `WorkingDirectory` and `ExecStart`
paths in the systemd files under [scripts/ops](scripts/ops).

### 3) Create the .env file

Create `/opt/autolycus/.env` with the following variables:

```
# Required core settings
api_key=YOUR_PNW_API_KEY
bot_token=YOUR_DISCORD_BOT_TOKEN
debug_channel=YOUR_DISCORD_CHANNEL_ID

# MongoDB
pymongolink=YOUR_MONGODB_URI
databaselink=YOUR_MONGODB_URI_FOR_MAIN_DB
version=YOUR_MONGODB_DB_NAME

# API config
FLASK_ENV=production
SECRET_KEY=CHANGE_ME_TO_A_LONG_RANDOM_VALUE
# Recommended behind the bundled Nginx proxy (see frontend/nginx.conf)
TRUST_PROXY_HEADERS=true

# PnW bot key (not the same as api_key); omit only if you do not need bot-key game API calls
bot_key=YOUR_PNW_BOT_KEY

# Same value in both services: bot uses X-Bot-Token; API validates in /api/auth/token/issue
DISCORD_BOT_API_KEY=CHANGE_ME_SHARED_SECRET_FOR_BOT_TO_API

# Optional: POST /api/auth/token/generate; if set, use the same value for VITE_AUTH_TOKEN_API_KEY below
AUTH_TOKEN_API_KEY=

# Optional tuning
WAITRESS_THREADS=8
WAITRESS_CONNECTION_LIMIT=200
WAITRESS_CHANNEL_TIMEOUT=30

# Frontend (build-time)
# Leave VITE_API_URL empty to use same-domain /api via Nginx proxy
VITE_API_URL=
# If you set AUTH_TOKEN_API_KEY above, set the same secret here so the SPA can call token generation
VITE_AUTH_TOKEN_API_KEY=

# Optional: Discord bot links and bot -> API HTTP (defaults: localhost:5173 + :5000)
# Production: same host as your site, origin only — no /api suffix (bot appends /api/...).
# AUTOLYCUS_WEB_BASE_URL=https://your-host
# AUTOLYCUS_API_BASE_URL=http://api:5000

# Optional: Caddy TLS (used when running Docker with `--profile prod`)
# SITE_DOMAIN=autolycus.your-domain.com
# ACME_EMAIL=you@your-domain.com
```

Notes:

- `databaselink` and `pymongolink` can be the same MongoDB URI if you use one cluster.
- `SECRET_KEY` must be set in production, otherwise tokens invalidate on restart.
- Docker images install Python deps from `requirements.txt` at the repo root. After changing dependencies in `pyproject.toml`, run `uv lock` and `uv export --format requirements-txt --no-dev --no-emit-project --no-hashes -o requirements.txt` before building.

### 4) Build and start the stack

```
docker compose build
docker compose up -d
```

For local Docker dev (frontend on `http://localhost:8080`):

```
docker compose up -d --build
```

With HTTPS via Caddy (recommended for production):

```
docker compose --profile prod up -d --build
```

In production (Docker `--profile prod`), Caddy serves the app publicly on `80/443` with TLS. In dev (default profile), frontend is served on `8080`. The API is accessible only through the
frontend reverse proxy at `/api` (not exposed directly on the host).

### 5) Enable auto-update + auto-restart (systemd)

This sets up:

- `autolycus.service` to start the Docker stack on boot.
- `autolycus-update.timer` to run a periodic update (git pull, rebuild, restart).

```
chmod +x scripts/ops/*.sh
sudo scripts/ops/bootstrap.sh
```

The update timer runs every 6 hours by default. Edit
[scripts/ops/autolycus-update.timer](scripts/ops/autolycus-update.timer) to change
the interval.

### 6) Firewall (Oracle Linux)

Allow inbound HTTP + HTTPS access:

```
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 7) Verify


When running for the first time a database file called `nations.db` will be created in `./data`. After running for ~30 minutes the bot should have updated the database with nation details for every nation. Until this happens, some functions may not work properly.

Docker uses the host `./data` folder as a bind mount. Ensure `./data/city_builds.db` exists on the host if you want builds to work immediately.

Common tasks:

```
docker compose ps
docker compose logs -f api
docker compose logs -f bot
docker compose logs -f scanner
docker compose logs -f frontend
```

Manual update (equivalent to the timer):

```
scripts/ops/update.sh
```

### MongoDB note

You still need a MongoDB database. A guide on how to set one up can be found
[here](https://docs.atlas.mongodb.com/getting-started/).

If you use the optional database updater repl, it still requires:

- `api_key`
- `pymongolink`
- `version`
- `ip`

### Helpful links

- https://docs.oracle.com/en/learn/use_systemd/index.html#work-with-systemd-timer-units
- https://docs.oracle.com/en/learn/lab_compute_instance/index.html