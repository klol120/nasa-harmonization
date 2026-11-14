-- Accounts and business features. None of this gates the data: every region endpoint stays public.

-- People who signed in (Google, or the local-only test login).
create table app_user (
    user_id        bigserial primary key,
    email          text not null,
    email_verified boolean not null default false,
    name           text,
    picture_url    text,
    google_sub     text unique,                    -- Google's stable account id
    created_at     timestamptz not null default now(),
    last_login_at  timestamptz
);
create unique index app_user_email_key on app_user (lower(email));

-- Sign-in sessions. Only a SHA-256 of the token is stored, so a database leak gives no usable tokens.
create table user_session (
    token_hash  bytea primary key,
    user_id     bigint not null references app_user on delete cascade,
    created_at  timestamptz not null default now(),
    expires_at  timestamptz not null,
    user_agent  text
);
create index user_session_user_idx on user_session (user_id);

-- Email list (no account needed). Double opt-in: 'pending' until the confirmation link is opened.
create table subscriber (
    subscriber_id    bigserial primary key,
    email            text not null,
    user_id          bigint references app_user on delete set null,
    status           text not null check (status in ('pending', 'confirmed', 'unsubscribed')),
    topics           text[] not null default '{news,digest}',
    token            text not null unique,         -- for the confirm / unsubscribe links
    source           text,                         -- where they signed up (landing, dashboard, account)
    created_at       timestamptz not null default now(),
    confirmed_at     timestamptz,
    unsubscribed_at  timestamptz
);
create unique index subscriber_email_key on subscriber (lower(email));

-- Areas a signed-in user saved, with their optional fire alert.
create table saved_area (
    area_id            bigserial primary key,
    user_id            bigint not null references app_user on delete cascade,
    region_id          text not null references region on delete cascade,
    name               text not null,
    kind               text not null check (kind in ('bbox', 'polygon')),
    bbox               double precision[] not null check (cardinality(bbox) = 4),
    ring               jsonb,                      -- [[lon, lat], ...] for polygons
    exclude_persistent boolean not null default false,
    alert_enabled      boolean not null default false,
    alert_z            double precision not null default 2.0 check (alert_z between 0.5 and 5),
    last_alerted_ym    date,                       -- newest month an alert was sent for
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);
create index saved_area_user_idx on saved_area (user_id);

-- Every email the app sends goes through here. Without SMTP settings nothing leaves the server and
-- the outbox can be read at /dev/outbox (local development only).
create table email_outbox (
    email_id    bigserial primary key,
    to_email    text not null,
    subject     text not null,
    body_text   text not null,
    body_html   text,
    kind        text not null,                     -- newsletter_confirm, alert, digest, ...
    created_at  timestamptz not null default now(),
    sent_at     timestamptz,
    error       text
);
create index email_outbox_unsent_idx on email_outbox (created_at) where sent_at is null;
