-- Controles desde el dashboard: agresividad por bot y operaciones manuales. Ejecutar después de 006. Es idempotente.
-- El dashboard nunca toca el exchange: solo deja órdenes en `commands`; el bot las valida y las ejecuta.

create table if not exists bot_controls (
    instance        text        primary key,
    aggressiveness  numeric     not null default 1 check (aggressiveness between 0.25 and 2),
    updated_at      timestamptz not null default now()
);

-- Historial de cambios: la tendencia lo usa para repetir el backtest con la misma agresividad de cada día.
create table if not exists control_changes (
    id              bigint generated always as identity primary key,
    instance        text        not null,
    aggressiveness  numeric     not null,
    changed_at      timestamptz not null default now()
);
create index if not exists control_changes_instance on control_changes (instance, changed_at);

create table if not exists commands (
    id            bigint generated always as identity primary key,
    kind          text        not null check (kind in ('agresividad', 'abrir', 'cerrar')),
    payload       jsonb       not null,
    status        text        not null default 'pendiente'
                  check (status in ('pendiente', 'ejecutando', 'hecha', 'rechazada', 'error')),
    result        text,
    created_at    timestamptz not null default now(),
    processed_at  timestamptz
);
create index if not exists commands_pending on commands (id) where status = 'pendiente';

alter table positions add column if not exists origin text not null default 'bot';
alter table positions add column if not exists aggressiveness numeric not null default 1;
do $$
begin
    if not exists (select from pg_constraint where conname = 'positions_origin_check') then
        alter table positions add constraint positions_origin_check check (origin in ('bot', 'manual'));
    end if;
end $$;

-- Usuario del dashboard para los controles: solo puede crear órdenes pendientes y leer su estado.
-- La contraseña se define con: python -m tradebot.publish --crear-operador
do $$
begin
    if not exists (select from pg_roles where rolname = 'dashboard_operator') then
        create role dashboard_operator login noinherit;
    end if;
end $$;

revoke all on all tables in schema public from dashboard_operator;
grant usage on schema public to dashboard_operator;
grant select on commands, bot_controls to dashboard_operator;
grant insert (kind, payload) on commands to dashboard_operator;

-- Supabase da permisos a anon/authenticated en tablas nuevas: con RLS y sin políticas para ellos, no ven nada.
alter table commands enable row level security;
alter table bot_controls enable row level security;
alter table control_changes enable row level security;
drop policy if exists operator_read on commands;
create policy operator_read on commands for select to dashboard_operator using (true);
drop policy if exists operator_insert on commands;
create policy operator_insert on commands for insert to dashboard_operator with check (status = 'pendiente');
drop policy if exists operator_read on bot_controls;
create policy operator_read on bot_controls for select to dashboard_operator using (true);

-- Además, sin permisos directos para los roles públicos de Supabase (si existen).
do $$
declare r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select from pg_roles where rolname = r) then
            execute format('revoke all on commands, bot_controls, control_changes from %I', r);
        end if;
    end loop;
end $$;
