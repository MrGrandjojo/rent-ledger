-- Rental property management database schema (v2.0)
-- All timestamps stored in UTC; displayed in Europe/Paris in the application.
-- Multi-user: roles + groups gate per-property access; landlord profile is per-user.

CREATE TABLE IF NOT EXISTS users (
    id                    SERIAL PRIMARY KEY,
    username              VARCHAR(50) UNIQUE NOT NULL,
    password_hash         VARCHAR(255) NOT NULL,
    force_password_change BOOLEAN DEFAULT true,
    role                  VARCHAR(20) NOT NULL DEFAULT 'user'
                            CHECK (role IN ('admin', 'supervisor', 'user')),
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    email                 VARCHAR(200),
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id              INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    landlord_name        VARCHAR(200) DEFAULT '',
    landlord_address     TEXT         DEFAULT '',
    landlord_phone       VARCHAR(20)  DEFAULT '',
    landlord_email       VARCHAR(200) DEFAULT '',
    signature_encrypted  TEXT,
    updated_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS properties (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    type            VARCHAR(20)  NOT NULL CHECK (type IN ('apartment', 'parking')),
    address_street  VARCHAR(200) NOT NULL,
    address_city    VARCHAR(100) NOT NULL,
    address_zip     VARCHAR(10)  NOT NULL,
    address_country VARCHAR(100) NOT NULL DEFAULT 'France',
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS groups (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_groups (
    user_id    INTEGER NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    group_id   INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_user_groups_group ON user_groups(group_id);

CREATE TABLE IF NOT EXISTS group_properties (
    group_id    INTEGER NOT NULL REFERENCES groups(id)     ON DELETE CASCADE,
    property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (group_id, property_id)
);
CREATE INDEX IF NOT EXISTS idx_group_properties_property ON group_properties(property_id);

CREATE TABLE IF NOT EXISTS tenants (
    id             SERIAL PRIMARY KEY,
    first_name     VARCHAR(100) NOT NULL,
    last_name      VARCHAR(100) NOT NULL,
    email          VARCHAR(200),
    phone          VARCHAR(20),
    guarantor_name VARCHAR(200),
    created_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS leases (
    id                       SERIAL PRIMARY KEY,
    property_id              INTEGER        NOT NULL REFERENCES properties(id),
    tenant_id                INTEGER        NOT NULL REFERENCES tenants(id),
    parent_lease_id          INTEGER        REFERENCES leases(id) ON DELETE SET NULL,
    lease_type               VARCHAR(20)    NOT NULL DEFAULT 'unfurnished'
                              CHECK (lease_type IN ('unfurnished', 'furnished', 'furnished_student')),
    start_date               DATE           NOT NULL,
    end_date                 DATE,
    security_deposit_amount  NUMERIC(10, 2),
    security_deposit_date    DATE,
    is_active                BOOLEAN        DEFAULT true,
    created_at               TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
-- Rent values are NOT stored on the lease; they live in rent_revisions.

CREATE TABLE IF NOT EXISTS rent_revisions (
    id              SERIAL PRIMARY KEY,
    lease_id        INTEGER        NOT NULL REFERENCES leases(id) ON DELETE CASCADE,
    effective_from  DATE           NOT NULL,
    monthly_rent    NUMERIC(10, 2) NOT NULL,
    monthly_charges NUMERIC(10, 2) NOT NULL DEFAULT 0,
    reason          VARCHAR(20)    NOT NULL DEFAULT 'initial'
                     CHECK (reason IN ('initial', 'irl_revision', 'amicable', 'other')),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (lease_id, effective_from)
);

CREATE TABLE IF NOT EXISTS payments (
    id               SERIAL PRIMARY KEY,
    lease_id         INTEGER        NOT NULL REFERENCES leases(id),
    year             INTEGER        NOT NULL,
    month            INTEGER        NOT NULL CHECK (month BETWEEN 1 AND 12),
    expected_amount  NUMERIC(10, 2) NOT NULL,
    received_amount  NUMERIC(10, 2) NOT NULL DEFAULT 0,
    payment_date     DATE,
    status           VARCHAR(20)    NOT NULL DEFAULT 'unpaid' CHECK (status IN ('paid', 'partial', 'unpaid')),
    outstanding_balance NUMERIC(10, 2) NOT NULL DEFAULT 0,
    notes            TEXT,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (lease_id, year, month)
);

CREATE TABLE IF NOT EXISTS charges_regularizations (
    id                          SERIAL PRIMARY KEY,
    lease_id                    INTEGER        NOT NULL REFERENCES leases(id),
    year                        INTEGER        NOT NULL,
    total_actual_charges        NUMERIC(10, 2) NOT NULL,
    total_provisions_collected  NUMERIC(10, 2) NOT NULL,
    balance                     NUMERIC(10, 2) NOT NULL,
    notes                       TEXT,
    created_at                  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (lease_id, year)
);

CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    lease_id    INTEGER      NOT NULL REFERENCES leases(id),
    type        VARCHAR(20)  NOT NULL CHECK (type IN ('rent_receipt', 'lease_scan', 'other')),
    file_name   VARCHAR(255) NOT NULL,
    stored_path VARCHAR(500) NOT NULL,
    upload_date TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id                  SERIAL PRIMARY KEY,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    user_id             INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_display_name   TEXT NOT NULL DEFAULT 'system',
    action              VARCHAR(20) NOT NULL
                          CHECK (action IN ('create', 'update', 'delete', 'export',
                                            'login', 'login_failed')),
    entity_type         VARCHAR(40) NOT NULL
                          CHECK (entity_type IN ('property', 'lease', 'tenant', 'payment',
                                                  'rent_revision', 'charge_regularization',
                                                  'document', 'user', 'group', 'audit_log',
                                                  'auth')),
    entity_id           TEXT,
    entity_label        TEXT,
    before              JSONB,
    after               JSONB,
    ip_address          TEXT
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_leases_property  ON leases(property_id);
CREATE INDEX IF NOT EXISTS idx_leases_tenant    ON leases(tenant_id);
CREATE INDEX IF NOT EXISTS idx_leases_active    ON leases(is_active);
CREATE INDEX IF NOT EXISTS idx_leases_parent    ON leases(parent_lease_id);
CREATE INDEX IF NOT EXISTS idx_payments_lease   ON payments(lease_id);
CREATE INDEX IF NOT EXISTS idx_payments_period  ON payments(year, month);
CREATE INDEX IF NOT EXISTS idx_charges_lease    ON charges_regularizations(lease_id);
CREATE INDEX IF NOT EXISTS idx_documents_lease  ON documents(lease_id);
CREATE INDEX IF NOT EXISTS idx_revisions_lease  ON rent_revisions(lease_id, effective_from);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at  ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user        ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity      ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action      ON audit_logs(action);
