-- Cuentas virtuales para estrategias que no mandan órdenes al exchange (p. ej. tendencia largo/corto).
-- Operan con precios reales y cobran comisión, slippage y funding. Ejecutar después de 005. Es idempotente.

create table if not exists paper_accounts (
    instance   text        primary key,
    cash       numeric     not null,
    last_day   date,                       -- último cierre diario procesado
    created_at timestamptz not null default now()
);

create table if not exists paper_holdings (
    instance text    not null references paper_accounts (instance),
    symbol   text    not null,
    qty      numeric not null,            -- negativo = corto
    primary key (instance, symbol)
);

create table if not exists paper_trades (
    id            bigserial   primary key,
    instance      text        not null references paper_accounts (instance),
    ts            timestamptz not null,
    symbol        text        not null,
    qty           numeric     not null,  -- cantidad operada (negativo = venta)
    price         numeric     not null,
    cost          numeric     not null,  -- comisión + slippage
    weight_before numeric     not null,
    weight_after  numeric     not null
);

create index if not exists paper_trades_instance_ts on paper_trades (instance, ts desc);
