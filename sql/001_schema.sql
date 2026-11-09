-- Esquema inicial. Ejecutar una vez en el SQL Editor de Supabase.
-- Todas las llaves naturales tienen restricción única para poder cargar con upsert (idempotente).

create table if not exists candles (
    symbol      text        not null,
    timeframe   text        not null,
    ts          timestamptz not null,
    open        numeric     not null,
    high        numeric     not null,
    low         numeric     not null,
    close       numeric     not null,
    volume      numeric     not null,
    primary key (symbol, timeframe, ts)
);

create table if not exists market_context (
    symbol         text        not null,
    ts             timestamptz not null,
    funding_rate   numeric,
    open_interest  numeric,
    fear_greed     smallint,
    headlines      jsonb       not null default '[]',
    primary key (symbol, ts)
);

create table if not exists features (
    symbol     text        not null,
    timeframe  text        not null,
    ts         timestamptz not null,
    indicators jsonb       not null,
    primary key (symbol, timeframe, ts)
);

create table if not exists signals (
    id          bigint generated always as identity primary key,
    instance    text        not null,
    strategy    text        not null,
    symbol      text        not null,
    timeframe   text        not null,
    ts          timestamptz not null,
    direction   text        not null check (direction in ('long', 'short')),
    score       numeric     not null,
    reason      text        not null,
    created_at  timestamptz not null default now(),
    unique (instance, strategy, symbol, timeframe, ts)
);

create table if not exists ai_reviews (
    id             bigint generated always as identity primary key,
    signal_id      bigint      not null unique references signals (id),
    model          text        not null,
    prompt         text        not null,
    response       jsonb,
    decision       text        check (decision in ('approve', 'reduce', 'veto')),
    error          text,
    input_tokens   integer,
    output_tokens  integer,
    duration_ms    integer,
    created_at     timestamptz not null default now()
);

create table if not exists positions (
    id           bigint generated always as identity primary key,
    instance     text        not null,
    signal_id    bigint      references signals (id),
    symbol       text        not null,
    side         text        not null check (side in ('long', 'short')),
    qty          numeric     not null,
    entry_price  numeric     not null,
    stop_price   numeric     not null,
    take_profit  numeric,
    exit_price   numeric,
    pnl          numeric,
    fees         numeric     not null default 0,
    status       text        not null default 'open' check (status in ('open', 'closed')),
    opened_at    timestamptz not null default now(),
    closed_at    timestamptz
);

create table if not exists orders (
    id                 bigint generated always as identity primary key,
    instance           text        not null,
    position_id        bigint      references positions (id),
    exchange_order_id  text        not null unique,
    symbol             text        not null,
    side               text        not null check (side in ('buy', 'sell')),
    order_type         text        not null,
    qty                numeric     not null,
    price              numeric,
    status             text        not null,
    fee                numeric,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);

create table if not exists bot_state (
    instance         text        primary key,
    mode             text        not null default 'operar' check (mode in ('operar', 'solo_cierre')),
    kill_switch      boolean     not null default false,
    aggressiveness   smallint    not null default 5 check (aggressiveness between 1 and 10),
    ai_calls_date    date,
    ai_calls_today   integer     not null default 0,
    last_heartbeat   timestamptz
);

create table if not exists learnings (
    id          bigint generated always as identity primary key,
    instance    text        not null,
    hypothesis  text        not null,
    status      text        not null default 'probando' check (status in ('probando', 'activa', 'descartada')),
    n_trades    integer     not null default 0,
    evidence    jsonb       not null default '{}',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists positions_open_idx on positions (instance) where status = 'open';
