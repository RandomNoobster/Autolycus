# About Autolycus

Autolycus is an open source bot for finding raid targets in PnW. It was initially developed for in-house usage, but I decided to make it public. As far as I am aware, no other public bots have extensive raid finding functionality. The lack of such functionality is what motivated me to make this public. Nonetheless, the fact that it was originally meant for in-house usage means multiple things. Firstly, it means that the code isn't pretty. Secondly, it means that it's not designed to be easy to self-host. 

## Production Docker deployment (Oracle Linux)

This project ships with a production-ready Docker setup that runs:

- Flask API (Waitress)
- Discord bot
- Scanner worker
- Frontend (Nginx + Vite build)

It also includes a systemd timer that regularly pulls the repo, rebuilds images,
and restarts services, so the stack stays up-to-date and resilient on crashes.

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
AUTH_TOKEN_API_KEY=

# Optional tuning
WAITRESS_THREADS=8
WAITRESS_CONNECTION_LIMIT=200
WAITRESS_CHANNEL_TIMEOUT=30

# Frontend (build-time)
# Leave VITE_API_URL empty to use same-domain /api via Nginx proxy
VITE_API_URL=
VITE_AUTH_TOKEN_API_KEY=
```

Notes:

- `databaselink` and `pymongolink` can be the same MongoDB URI if you use one cluster.
- `SECRET_KEY` must be set in production, otherwise tokens invalidate on restart.

### 4) Build and start the stack

```
docker compose build
docker compose up -d
```

The frontend is served on port 80. The API is accessible only through the
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

Allow inbound HTTP access:

```
sudo firewall-cmd --permanent --add-service=http
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