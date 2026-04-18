---
globs: ["Dockerfile", "docker-compose*.yml", "zeabur.json", ".env*", "backend/app/config.py"]
---

# Deployment Rules

- Never commit .env — use .env.example as template
- All env vars loaded through config.py (Pydantic BaseSettings) — never os.getenv() inline
- Zeabur private networking: use service names as hostnames for internal services (e.g. redis)
- GET /health must always return 200 with { status: 'ok', timestamp: ISO8601 }
- CORS: restrict to frontend domain in production (not *)
- Celery broker URL: redis://redis:6379/0 (uses Zeabur private network)
- PostgreSQL: hosted on Supabase (external, not Zeabur) — POSTGRES_CONNECTION_STRING must be set manually in Zeabur service Variables tab for BOTH backend and worker services
- Supabase connection: use Session pooler on port 5432 (aws-1-ap-northeast-1.pooler.supabase.com). Switch to Transaction pooler on port 6543 with ?pgbouncer=true only if prepared-statement errors occur
- Supabase traffic crosses the public internet (no Zeabur private networking) — deploy Zeabur services in a region close to ap-northeast-1 (Tokyo) to minimize latency
