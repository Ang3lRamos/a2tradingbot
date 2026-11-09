-- Usuario de solo lectura para el dashboard web (Vercel): solo puede leer dashboard_snapshots.
-- Ejecutar después de 004. La contraseña se define con: python -m tradebot.publish --crear-lector
-- La contraseña nunca va en este archivo.
do $$
begin
    if not exists (select from pg_roles where rolname = 'dashboard_reader') then
        create role dashboard_reader login noinherit;
    end if;
end $$;

revoke all on all tables in schema public from dashboard_reader;
grant usage on schema public to dashboard_reader;
grant select on dashboard_snapshots to dashboard_reader;
