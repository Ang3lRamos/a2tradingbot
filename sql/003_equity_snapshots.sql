-- Fase 5: historial de capital para el dashboard. Ejecutar después de 002. Es idempotente.

create table if not exists equity_snapshots (
    instance  text        not null,
    ts        timestamptz not null,
    equity    numeric     not null,
    primary key (instance, ts)
);
