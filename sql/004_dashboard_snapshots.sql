-- Fase 5: datos ya calculados para el dashboard web (Vercel). Ejecutar después de 003. Es idempotente.
-- El bot escribe aquí al final de cada ciclo; el dashboard solo lee esta tabla.

create table if not exists dashboard_snapshots (
    key         text        primary key,   -- resumen | ia | backtest_is | backtest_oos
    data        jsonb       not null,
    updated_at  timestamptz not null default now()
);
