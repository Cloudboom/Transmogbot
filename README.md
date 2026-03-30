# Discord Transmog Bot

A Discord bot for collecting transmog themes and selecting one automatically on a cron schedule.

## Features

- Submit new themes with `!tmnew <theme>`.
- Weekly/random theme selection via cron.
- See all themes with `!tmall`.
- See submission counts with `!tmuser`.
- Enable/disable notifications with `!tmnotify` and `!tmnotifyoff`.
- Toggle output with `!tmon` and `!tmoff`.

## Environment

Create a `.env` file with:

```env
CHANNEL_ID=
BOT_TOKEN=
```

## Docker Compose Setup

1. Create a `docker-compose.yml` with this content:
```yaml
services:
  transmogbot:
    image: ghcr.io/cloudboom/transmogbot:latest
    container_name: transmogbot
    restart: unless-stopped
    environment:
      PYTHONUNBUFFERED: "1"
      DB_PATH: /data/main.sqlite
      CRON_SCHEDULE: "0 19 * * 0"
      CRON_TZ: YOUR_TIMEZONE
    env_file:
      - /your/path/.env
    volumes:
      - /your/path/data:/data
```
2. Adjust paths and image name to your environment.
3. Start or update the container:
```bash
docker compose pull
docker compose up -d
```
