import "server-only";

import { cacheLife } from "next/cache";
import { Pool } from "pg";

import type { DashboardData } from "./types";

// Usuario de solo lectura: solo puede leer dashboard_snapshots (ver sql/005_dashboard_reader.sql).
let pool: Pool | undefined;

function getPool(): Pool {
  const connectionString = process.env.DASHBOARD_DATABASE_URL;
  if (!connectionString) throw new Error("Falta DASHBOARD_DATABASE_URL");
  pool ??= new Pool({ connectionString, max: 2, ssl: { rejectUnauthorized: false } });
  return pool;
}

export async function getDashboardData(): Promise<DashboardData> {
  "use cache";
  // El bot publica una vez por hora; refrescar cada minuto es de sobra.
  cacheLife("minutes");

  const { rows } = await getPool().query<{ key: string; data: unknown; updated_at: Date }>(
    "select key, data, updated_at from dashboard_snapshots",
  );
  const byKey = Object.fromEntries(rows.map((r) => [r.key, r.data]));
  const resumen = rows.find((r) => r.key === "resumen");
  return {
    resumen: (byKey.resumen as DashboardData["resumen"]) ?? null,
    ia: (byKey.ia as DashboardData["ia"]) ?? null,
    backtest_is: (byKey.backtest_is as DashboardData["backtest_is"]) ?? null,
    backtest_oos: (byKey.backtest_oos as DashboardData["backtest_oos"]) ?? null,
    actualizado: resumen ? resumen.updated_at.toISOString() : null,
  };
}
