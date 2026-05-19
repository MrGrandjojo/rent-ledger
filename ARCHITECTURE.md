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
  `(rent_receipt|lease_scan|other)`, `file_name`, `stored_path`
  (relative inside `/app/uploads`), `upload_date`.
- **audit_logs** — append-only. `id`, `created_at`, `user_id` FK SET NULL,
  `user_display_name` (snapshot), `action` ∈
  `(create|update|delete|export|login|login_failed)`, `entity_type` ∈
  `(property|lease|tenant|payment|rent_revision|charge_regularization|document|user|group|audit_log|auth)`,
  `entity_id`, `entity_label` (snapshot), `before` JSONB, `after` JSONB,
  `ip_address`. Application code must NOT issue UPDATE or DELETE on this
  table outside the admin-only purge endpoint. Writes go through
  `app.audit_log.log_event`. **Only admin logins and failed logins are
  recorded** — successful user/supervisor logins and all logouts are not.

**Relationships**: User 1→1 UserProfile; User N↔N Groups; Group N↔N
Properties; Property 1→N Leases; Tenant 1→N Leases; Lease 1→N
RentRevisions / Payments / ChargesRegularizations / Documents.

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
