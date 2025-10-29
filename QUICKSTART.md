# Quick Start Guide

## Prerequisites

- Docker & Docker Compose installed
- Port 8080 available

## 1. Setup

```bash
# Clone the repository
cd Open-Library-Format

# Copy environment template (CRITICAL: edit .env and change APP_SECRET!)
cp .env.example .env
nano .env  # or your preferred editor

# Build and start
docker-compose up -d
```

## 2. Bootstrap

```bash
# Check logs for bootstrap token
docker-compose logs app | grep "Token:"

# You'll see something like:
# Bootstrap mode active. Token: abc123...
# Visit http://127.0.0.1:8080/setup?token=abc123...
```

Open the URL in your browser and create your admin account.

## 3. Create Your First Library

1. After login, click "Create Library"
2. Name: "My Photos"
3. Type: "Photos & Videos"
4. Timezone: Your local timezone (e.g., "America/New_York")
5. Click "Create"

## 4. Upload Files

1. Click "Browse" on your library
2. Click "Upload Files"
3. Select photos or videos
4. Wait for upload to complete
5. Thumbnails will generate automatically

## 5. Organize with Tags

1. Go to a library
2. Create tags like "Favorites", "Vacation"
3. Add tags to files
4. Filter by tag using the tag chips

## Common Commands

```bash
# View logs
docker-compose logs -f app

# Stop the app
docker-compose down

# Restart after config change
docker-compose restart

# Create user via CLI (bypass wizard)
docker exec app python -m app.cli create-user --admin myuser mypassword

# Backup a library
cp -r libraries/my-photos /backup/my-photos-$(date +%Y%m%d)

# Use slim image (no ffmpeg/exiftool)
docker-compose -f docker-compose.yml -f compose.slim.yml up -d
```

## File Locations

- **Libraries**: `./libraries/` (mounted from host)
- **Registry DB**: `./var/registry.db`
- **Logs**: `docker-compose logs app`
- **Bootstrap sentinel**: `./var/bootstrap_done`

## Troubleshooting

### "Bootstrap mode active" after setup
Check if `./var/bootstrap_done` exists. If not, complete setup or create it manually:
```bash
mkdir -p var && touch var/bootstrap_done
docker-compose restart
```

### Thumbnails not showing
- Check logs for errors: `docker-compose logs app | grep -i error`
- If using `:slim` image, video thumbnails won't work (need `:full`)
- Wait a few seconds after upload for thumbnail generation

### Can't login
- Check username/password
- Clear browser cookies
- Check logs: `docker-compose logs app`

### Upload fails
- Check file size (default max: 512MB in .env)
- Verify file type matches library type
- Check disk space: `df -h`

## Next Steps

- Read [README.md](README.md) for full documentation
- Review [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
- Run acceptance tests: `python tests/acceptance.py`

## Production Checklist

- [ ] Change `APP_SECRET` in .env (critical!)
- [ ] Set up reverse proxy (nginx/Caddy) for HTTPS
- [ ] Configure firewall rules
- [ ] Set appropriate `DEFAULT_TZ`
- [ ] Test backup/restore procedure
- [ ] Enable monitoring of `/api/health`

