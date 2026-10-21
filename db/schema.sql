CREATE TABLE IF NOT EXISTS members (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'staff')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS members_email_lower ON members (lower(email));

CREATE TABLE IF NOT EXISTS books (
    id           BIGSERIAL PRIMARY KEY,
    isbn         TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    author       TEXT NOT NULL,
    year         INTEGER,
    total_copies INTEGER NOT NULL CHECK (total_copies >= 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS loans (
    id          BIGSERIAL PRIMARY KEY,
    member_id   BIGINT NOT NULL REFERENCES members (id),
    book_id     BIGINT NOT NULL REFERENCES books (id),
    borrowed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    due_at      TIMESTAMPTZ NOT NULL,
    returned_at TIMESTAMPTZ,
    renewals    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS loans_active_book ON loans (book_id) WHERE returned_at IS NULL;
CREATE INDEX IF NOT EXISTS loans_member ON loans (member_id);

CREATE TABLE IF NOT EXISTS holds (
    id          BIGSERIAL PRIMARY KEY,
    member_id   BIGINT NOT NULL REFERENCES members (id),
    book_id     BIGINT NOT NULL REFERENCES books (id),
    status      TEXT NOT NULL DEFAULT 'waiting'
                CHECK (status IN ('waiting', 'ready', 'fulfilled', 'cancelled', 'expired')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ready_until TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS holds_book_status ON holds (book_id, status);

CREATE TABLE IF NOT EXISTS fees (
    id           BIGSERIAL PRIMARY KEY,
    member_id    BIGINT NOT NULL REFERENCES members (id),
    loan_id      BIGINT NOT NULL REFERENCES loans (id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS fees_member ON fees (member_id);
