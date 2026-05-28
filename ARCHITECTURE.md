# Architecture

Reference for the data model, business rules and security model of the
Rental app. Read this before making non-trivial changes.

---

## Stack

- **Backend** — FastAPI 0.115, Uvicorn 0.30, SQLAlchemy 2, psycopg2-binary 2.9
- **Frontend** — React 18 (Vite 5), Tailwind 3, React Router 6, Axios
- **Auth** — JWT HS256 (8 h), HttpOnly `SameSite=Lax` cookie, optional `Secure`,
  bcrypt cost 12, rate limit on `/login`
- **Crypto** — `cryptography` 43 (AES-256-GCM for landlord signatures)
- **PDF** — fpdf2 2.8 (core Helvetica is Latin-1, see note below)
- **Scheduler** — APScheduler 3.10 (BackgroundScheduler, server timezone)
- **DB** — PostgreSQL 16
- **Web** — Nginx (frontend container)

---

## Conventions

- UI language: **French** (all user-facing text)
- Code language: **English** (variables, functions, comments, files,
  commits, API routes, DB columns)
- All timestamps stored in UTC and displayed in the configured server timezone
  (default `Europe/Paris` in the containers).
- Currency: Euros, 2 decimal places.

---

## Data model

Full DDL in [db/init.sql](db/init.sql). Summary:

- **users** — `id`, `username` UNIQUE, `password_hash` (bcrypt),
  `force_password_change`, `role` ∈ `(admin|supervisor|user)`, `is_active`,
  `email`, `created_at`. Admin and supervisor bypass property scoping; admin
  is the only role allowed to manage `audit_logs`.
- **user_profiles** — 1-1 with `users`. `landlord_name`, `landlord_address`,
  `landlord_phone`, `landlord_email`, `signature_encrypted`
  (base64 of AES-256-GCM `nonce ‖ ciphertext+tag`), `updated_at`. Used on PDF
  receipts.
- **groups** — `id`, `name` UNIQUE, `description`, `created_at`.
- **user_groups** — composite PK `(user_id, group_id)`.
- **group_properties** — composite PK `(group_id, property_id)`.
- **properties** — `id`, `name`, `type` ∈ `(apartment|parking)`,
  `address_street`, `address_city`, `address_zip`, `address_country`
  (default `France`), `created_at`.
- **tenants** — `id`, `first_name`, `last_name`, `email?`, `phone?`,
  `guarantor_name?`, `created_at`.
- **leases** — `id`, `property_id` FK, `tenant_id` FK, `parent_lease_id` FK
  (nullable, ON DELETE SET NULL — marks amendments), `lease_type` ∈
  `(unfurnished|furnished|furnished_student)`, `start_date`, `end_date`
  (auto-computed; amendments inherit live from parent),
  `security_deposit_amount?`, `security_deposit_date?`, `is_active`,
  `created_at`. **No rent columns** — they live in `rent_revisions` only.
- **rent_revisions** — `id`, `lease_id` FK (CASCADE), `effective_from`,
  `monthly_rent`, `monthly_charges`, `reason` ∈
  `(initial|irl_revision|amicable|other)`, `created_at`.
  UNIQUE `(lease_id, effective_from)`.
- **payments** — `id`, `lease_id` FK, `year`, `month`, `expected_amount`,
  `received_amount`, `payment_date?`, `status` ∈ `(paid|partial|unpaid)`,
  `outstanding_balance`, `notes?`, `created_at`.
  UNIQUE `(lease_id, year, month)`.
- **charges_regularizations** — `id`, `lease_id` FK, `year`,
  `total_actual_charges`, `total_provisions_collected`, `balance`, `notes?`,
  `created_at`. UNIQUE `(lease_id, year)`.
- **documents** — `id`, `lease_id` FK, `type` ∈
  `(rent_receipt|lease_scan|commandement_payer|other)`, `file_name`,
  `stored_path` (relative inside `/app/uploads`), `upload_date`.
- **procedures** — `id`, `lease_id` FK CASCADE, `parent_procedure_id` FK
  SET NULL (extensible chaining: a `commandement_payer` may later spawn
  an `assignation`, etc.), `procedure_type` ∈ `(commandement_payer)`,
  `notification_date`, `deadline_date` (auto = `notification_date + 2
  months` for CDP per art. 24 loi du 6 juillet 1989; editable),
  decomposed amounts `amount_rent`, `amount_fees`, `amount_other`,
  `status` ∈ `(in_progress|paid|expired_unpaid|cancelled)`,
  `bailiff_name?`, `act_reference?`, `notes?`, `created_at`,
  `updated_at`. CHECK `deadline_date >= notification_date`.
- **procedure_payments** — manual imputation of a Payment to a
  Procedure. Composite PK `(procedure_id, payment_id)` (both CASCADE).
  Used when a payment falling **outside** `[notification_date,
  deadline_date]` must still count toward solving the procedure
  (typical case: rent paid between the day the landlord requests the
  act and the day the bailiff serves it). Payments **inside** the
  window are imputed automatically and not stored here.
- **audit_logs** — append-only, **PARTITIONED BY RANGE (`created_at`)**,
  one partition per year (`audit_logs_YYYY`). PK is `(id, created_at)`
  as required by the partition key. The boot job
  `ensure_audit_partitions` in `app/scheduler.py` provisions the
  current-year + next-year partitions automatically; a monthly job
  (day-1 02:00 server time) does the same in steady state. To archive
  an old year: `ALTER TABLE audit_logs DETACH PARTITION
  audit_logs_YYYY;` then `COPY` it out and `DROP TABLE` — fully manual,
  no automatic retention.
  Columns: `id`, `created_at`, `user_id` FK SET NULL,
  `user_display_name` (snapshot), `action` ∈
  `(create|update|delete|export|login|login_failed)`, `entity_type` ∈
  `(property|lease|tenant|payment|rent_revision|charge_regularization|document|user|group|audit_log|auth|procedure)`,
  `entity_id`, `entity_label` (snapshot), `before` JSONB, `after` JSONB,
  `ip_address`. Application code must NOT issue UPDATE or DELETE on this
  table outside the admin-only purge endpoint. Writes go through
  `app.audit_log.log_event`. **Only admin logins and failed logins are
  recorded** — successful user/supervisor logins and all logouts are not.

**Relationships**: User 1→1 UserProfile; User N↔N Groups; Group N↔N
Properties; Property 1→N Leases; Tenant 1→N Leases; Lease 1→N
RentRevisions / Payments / ChargesRegularizations / Documents /
Procedures; Procedure self-ref (parent/child for future chaining);
Procedure N↔N Payments via `procedure_payments`.

---

## Business rules

- **Effective rent**: for `(lease, year, month)`, pick the `rent_revisions`
  row with the latest `effective_from ≤ first day of (year, month)`.
  Expected = `monthly_rent + monthly_charges`. No code path reads rent from
  `leases` — the columns no longer exist. Missing revision → HTTP 500 (don't
  silently fall back). Centralised in `backend/app/lease_rules.py`
  (`effective_revision_for`, `expected_amount_for`).
- **Lease type defaults** (`backend/app/lease_rules.py`):
  `unfurnished` → 3 yr / 6 mo notice; `furnished` → 1 yr / 3 mo;
  `furnished_student` → 9 mo / 3 mo.
- **Tacit renewal**: stand-alone / parent leases roll `end_date` forward by
  one default duration when `today > end_date` and `is_active`. Amendments
  inherit live from parent (`resolve_end_date`); never read the stored value
  on a child.
- **Amendments**: `parent_lease_id IS NOT NULL`. Inherit `lease_type` and
  `end_date`. Own rent_revisions, tenant, start_date, is_active. Single-level
  nesting; parent cannot be deleted while it has amendments (HTTP 409).
- **Form-edit ↔ initial revision sync**: creating a lease writes the form's
  rent/charges as a new `rent_revisions` row tagged `reason='initial'`,
  `effective_from = start_date`. Editing those fields updates the existing
  `initial` row in place. Helper: `app.lease_rules.upsert_initial_revision`.
- **Server-authoritative expected_amount**: `POST /api/payments` recomputes
  `expected_amount` from `rent_revisions` and ignores any client value.
- **Scheduler — auto-generated unpaid payments**: `app/scheduler.py`
  `BackgroundScheduler`. Job `create_monthly_payments` at cron `01:00`,
  plus catch-up at boot. For each active lease, fills in missing Payment
  rows from `start_date` up to and **including the previous month** (the
  current month is **never** auto-written). Each insert: `status='unpaid'`,
  `received_amount=0`, `expected_amount` from effective revision,
  `notes='Généré automatiquement'`, audit `user_display_name='Système'`,
  `after.origin='scheduler'`. Idempotent.
- **Dashboard projection vs scheduler**: the dashboard treats the current
  month as due from day one — any active lease without a Payment row for
  `(current_year, current_month)` is projected as `status='unpaid',
  outstanding=expected`. The scheduler does not write it until the month
  ends.
- **Net outstanding (all-months)**: `outstanding_total =
  max(0, Σ expected − Σ received)` over **all** Payments of the lease, plus
  the current-month projection if missing. This is the only formula that
  applies an overpayment surplus against arrears (the per-row
  `outstanding_balance` clamps at 0).
- **Payments listing**: `GET /api/payments` returns a
  `PaginatedPaymentsOut` envelope `{items, total, page, page_size}` —
  never a raw list. Defaults `page=1`, `page_size=50`, hard cap 500.
  Sort is `(year DESC, month DESC, property.name ASC, tenant.last_name
  ASC, tenant.first_name ASC, lease_id ASC)` so the same lease keeps
  the same visual slot from one month to the next.
- **Hot-path batching**: dashboard and `GET /api/leases` use batched
  helpers (`batch_effective_revisions`, `batch_initial_revisions` in
  `lease_rules.py`) + pre-loaded property/tenant/parent maps so the
  cost is `O(1)` SQL roundtrips instead of `O(n_leases)`. Same pattern
  for `GET /api/procedures` via `_batch_to_out`.
- **Procedures (CDP)**: status is **recomputed on every read** from
  the attached payments + dates and returned to clients in memory. The
  persisted `status` column is **never** written from a GET handler;
  it is converged by the `refresh_procedure_statuses` job in
  `app/scheduler.py` (daily at 01:30 server time + boot catch-up).
  Rules in `procedure_rules.py`:
  - `total_due = amount_rent + amount_fees + amount_other`.
  - `total_paid = Σ received_amount` over attached payments.
  - Attached = **auto** (any Payment of the lease whose
    `payment_date ∈ [notification_date, deadline_date]`, computed on
    the fly, never stored) **+ manual** (rows in `procedure_payments`).
  - `paid` iff `total_paid ≥ total_due` AND latest contributing
    `payment_date ≤ deadline_date`.
  - `expired_unpaid` iff `today > deadline_date` and not paid/cancelled.
  - `cancelled` is sticky (manual state via
    `POST /api/procedures/{id}/cancel`).
  - Else `in_progress`.
- **CDP default deadline**: for `procedure_type='commandement_payer'`,
  `deadline_date = notification_date + 2 months` (with day clamping for
  short months). Auto-filled by both server and frontend; the user can
  override if the act states a different delay.
- **Scheduler — procedure status refresh**: same scheduler, job
  `refresh_procedure_statuses` at cron `01:30`, plus boot catch-up.
- **Scheduler — audit partitions**: job `ensure_audit_partitions` at
  cron `day-1 02:00`, plus boot catch-up. Creates yearly partitions for
  `current_year` and `current_year+1` if missing — a write hitting a
  date with no partition would fail.

---

## Access control

- Property visibility for `role='user'`: there must exist ≥1 group G such
  that `(user, G) ∈ user_groups AND (G, property) ∈ group_properties`. All
  downstream resources inherit. Tenant deletion requires that every linked
  property is accessible.
- `admin` / `supervisor` bypass the filter via `has_global_access(user)` in
  `dependencies.py`. Out-of-scope → HTTP 404 (not 403) to avoid leaking
  existence.
- Property create / update / delete: `require_admin_or_supervisor`.
- `audit_logs` (list / export / purge): `require_admin` only. Supervisors
  get 403.
- Supervisor cannot create / promote-to / demote / deactivate / delete an
  admin (enforced in `routers/admin.py`).
- Admin demotion blocked when it would leave zero active admins.
- Deactivated users (`is_active=false`) rejected at login and on every
  request.
- `force_password_change=True` blocks every authenticated endpoint except
  `GET /api/auth/me` and `PUT /api/auth/change-password` until the user
  picks a new password.
- Procedures (CDP): visibility, create/edit/cancel and payment
  attach/detach are gated by `assert_lease_access` — any user
  (including `role='user'`) with access to the underlying lease can
  manage the procedure. **Deletion** (`DELETE /api/procedures/{id}`)
  is restricted to `require_admin_or_supervisor` — irreversible action
  on legal data.
- Payments: list / create / update / partial actions remain open to
  any user with lease access. **Deletion**
  (`DELETE /api/payments/{id}`) is restricted to
  `require_admin_or_supervisor` — preserves history and the cumulative
  balance arithmetic.

---

## Security

- Passwords: bcrypt cost 12. JWT HS256, 8 h, HttpOnly `SameSite=Lax` cookie;
  `Secure` flag toggled by the `COOKIE_SECURE` env var.
- `/api/auth/login` rate-limited to 5 attempts per minute per IP via
  `slowapi`.
- Signature encryption key: `SIGNATURE_ENCRYPTION_KEY` = `openssl rand -hex
  32`, loaded from `.env`. Backend fails fast if missing or malformed. Never
  logged, never returned in any API response.
- Signature pipeline: upload → in-memory validate (PNG/JPG ≤ 500 KB, Pillow
  `verify()` + re-encode to drop EXIF) → AES-256-GCM (12-byte random nonce)
  → base64 store. Plaintext never persisted. Render decrypts in memory,
  embeds via `pdf.image(BytesIO(...))`, drops. Blurred preview goes through
  Pillow `ImageFilter.GaussianBlur(radius=6)` then streams PNG — no disk
  artefact.
- `audit_logs.action`: only **admin** successful logins and **all** failed
  logins are recorded. Regular user / supervisor logins and all logouts are
  not, to keep the log focused on signals (modifications + auth anomalies).
- Document upload pipeline (`POST /api/documents`): early
  `Content-Length` gate → hard cap **25 MB** (`MAX_UPLOAD_BYTES` in
  `routers/documents.py`, mirrored by nginx `client_max_body_size
  25M`) → **magic-number content sniffing** (PDF / PNG / JPG only —
  extension ignored, defends against `evil.pdf` masquerading) →
  UUID-named file with the sniffed extension written to
  `/app/uploads`.

---

## Concurrency & scaling

- **Multi-worker uvicorn** — the Dockerfile starts uvicorn with
  `--workers ${UVICORN_WORKERS:-4}`. Each worker is a separate Python
  process; the GIL no longer serialises bcrypt / PDF generation / SQL
  across HTTP calls.
- **Scheduler election** — with multiple workers, only one runs the
  APScheduler instance and the boot-time catch-ups (file lock on
  `/tmp/rental-scheduler.lock`, `fcntl.LOCK_EX | LOCK_NB`). Others
  serve the API only. Self-healing: if the elected worker dies, the
  next boot of another worker acquires the lock. Single-host only —
  multi-host deployments would need a distributed lock (Redis,
  Postgres advisory).
- **DB pool** — `pool_size=10, max_overflow=5, pool_recycle=1800`.
  At 4 workers that's up to ~60 connections in burst, well under
  PostgreSQL's default `max_connections=100`. `pool_recycle` cuts idle
  connections before PostgreSQL's 1h idle timeout kicks them.

---

## Monitoring

- `/api/metrics` (unauthenticated, intended for an internal scraper)
  exposes Prometheus metrics via `prometheus-fastapi-instrumentator`:
  - HTTP request histograms (latency, count, in-progress, status) —
    **per-worker** because each uvicorn worker has its own registry.
    Acceptable for a single host with a few users; Grafana aggregates
    over time. For multi-host setups, use multiprocess mode or push
    to a central registry.
  - Seven business gauges defined in `app/metrics.py` refreshed **on
    every scrape** by the worker that responds (7 `SELECT COUNT(*)`,
    negligible at a 15s scrape interval): `rental_active_leases`,
    `rental_properties_total`, `rental_tenants_total`,
    `rental_cdp_in_progress`, `rental_cdp_expired_unpaid`,
    `rental_payments_unpaid_current_month`,
    `rental_audit_logs_total`.
- Block external access to `/api/metrics` at the reverse proxy if the
  host is internet-facing.

---

## Deployment

See [README.md](README.md) for the quick-start. The compose file declares
three services on two internal networks:

- `backend` (internal) — backend ↔ database; not reachable from outside.
- `proxy` (internal) — frontend ↔ backend; the frontend container also
  exposes port 80 to the host (default mapping `8080:80`).

Backups are out of scope of the app itself — run `pg_dump` on a schedule
from the host or a sidecar.

### PDF font note

fpdf2's bundled Helvetica is Latin-1 only. The receipt template uses
`"EUR"` rather than the `€` glyph for that reason. If you need full
Unicode, bundle a TTF (DejaVu, NotoSans) and switch via
`pdf.add_font(...)` + `pdf.set_font(...)`.
