# Rental — Rental Property Management

Self-hosted web app to manage rental properties, tenants, leases, monthly
payments, charges regularization and PDF rent receipts. Multi-user with
role-based access control (admin / supervisor / user) and per-user landlord
profile with encrypted signature.

> French UI, English code. See [ARCHITECTURE.md](ARCHITECTURE.md) for the data
> model and business rules.

---

## Features

- Properties, tenants, leases (with amendments / *avenants*), rent revisions
  with IRL-style anniversary tracking, tacit renewal.
- Monthly payment tracking with auto-generated unpaid rows (catch-up at boot
  and daily at 01:00 server-time) and bulk retroactive entry.
- Charges regularization (per lease, per year).
- PDF rent receipt generation, with optional landlord signature embedded
  (encrypted at rest with AES-256-GCM).
- Document upload (lease scans, receipts, other) with per-property access
  scoping.
- Admin / supervisor management UI for users, groups and property scoping.
- Append-only audit log with CSV export (admin-only).

## Tech stack

- **Backend** — FastAPI 0.115, SQLAlchemy 2, PostgreSQL 16
- **Frontend** — React 18, Vite 5, Tailwind 3, React Router 6
- **Auth** — JWT HS256 in an HttpOnly cookie (`SameSite=Lax`, `Secure` opt-in),
  bcrypt cost 12, rate-limiting on `/login`
- **Crypto** — AES-256-GCM for signatures, key in env
- **PDF** — fpdf2 2.8
- **Scheduler** — APScheduler 3.10 (monthly payment generation)
- **Container** — Docker Compose (also works under Podman with `podman compose`)

---

## Quick start

Requirements: Docker 24+ with the Compose plugin (or Podman 4+ with
`podman compose`). All commands assume you cloned the repo at
`/opt/rental` — adjust paths to taste.

```bash
git clone https://github.com/<your-user>/rental.git /opt/rental
cd /opt/rental

# 1. Generate the three required secrets
cp .env.example .env
{
  echo "SIGNATURE_ENCRYPTION_KEY=$(openssl rand -hex 32)"
  echo "SECRET_KEY=$(openssl rand -hex 32)"
  echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"
} >> .env
chmod 600 .env

# 2. Build & start the stack
docker compose up -d --build

# 3. Open http://localhost:8080
#    Default credentials: admin / admin123 (forced change on first login)
```

The compose file binds the frontend to host port `8080` by default. Change
that mapping in `docker-compose.yml` if you put the app behind a reverse
proxy.

### Putting it behind a reverse proxy

The app is path-prefix aware: the FastAPI app uses `root_path="/rental"` and
the React frontend expects to be served under any path. Typical Caddy /
Traefik / nginx config strips the prefix and forwards the rest to the
`rental-frontend` container's port 80.

### Production hardening checklist

Before exposing the app on the public internet:

1. Set `COOKIE_SECURE=true` in `.env` (requires HTTPS).
2. Place the stack behind a TLS-terminating reverse proxy.
3. Review the security headers in [frontend/nginx.conf](frontend/nginx.conf) and
   tighten the CSP if you add new external resources.
4. Set up regular DB backups
   (`docker compose exec rental-db pg_dump -U rental rental > backup.sql`).
5. Change the default admin password immediately after first login (the app
   enforces this on first connection, but verify it happened).

---

## Updating

```bash
cd /opt/rental
git pull
docker compose up -d --build
```

Schema changes are applied automatically by the backend on startup
(`db/init.sql` is idempotent thanks to `CREATE TABLE IF NOT EXISTS`).

---

## Project structure

```
backend/        FastAPI app + SQLAlchemy models + routers
  app/
    routers/   one file per resource (auth, properties, leases, …)
    main.py    app factory + lifespan + scheduler bootstrap
frontend/       React SPA (Vite + Tailwind)
  src/
    pages/     one file per top-level route
    components/
db/             init.sql (full schema)
docker-compose.yml
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the data model, business rules and
security guarantees.

---

## License

MIT — see [LICENSE](LICENSE).
