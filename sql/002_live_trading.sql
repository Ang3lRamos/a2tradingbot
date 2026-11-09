-- Fase 4: estado de riesgo y datos de ejecución. Ejecutar una vez en el SQL Editor de Supabase,
-- después de 001_schema.sql. Es idempotente.

alter table bot_state add column if not exists mode_reason      text;
alter table bot_state add column if not exists equity_peak      numeric;
alter table bot_state add column if not exists day_start_equity numeric;
alter table bot_state add column if not exists risk_day         date;
alter table bot_state add column if not exists last_cycle_bar   timestamptz;

alter table positions add column if not exists risk_distance    numeric;
alter table positions add column if not exists size_multiplier  numeric not null default 1;
alter table positions add column if not exists stop_order_id    text;
alter table positions add column if not exists exit_reason      text;

create table if not exists alerts (
    id          bigint generated always as identity primary key,
    instance    text        not null,
    level       text        not null check (level in ('info', 'warning', 'critical')),
    message     text        not null,
    created_at  timestamptz not null default now()
);
