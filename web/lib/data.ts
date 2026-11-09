import "server-only";

import { cacheLife } from "next/cache";
import { Pool } from "pg";

import type { DashboardData } from "./types";

// Usuario de solo lectura: solo puede leer dashboard_snapshots (ver sql/005_dashboard_reader.sql).
let pool: Pool | undefined;

const EMPTY: DashboardData = { resumen: null, ia: null, backtest_is: null, backtest_oos: null, actualizado: null, error: null };

export async function getDashboardData(): Promise<DashboardData> {
  "use cache";
  // El bot publica una vez por hora; refrescar cada minuto es de sobra.
  cacheLife("minutes");

  const connectionString = process.env.DASHBOARD_DATABASE_URL;
  if (!connectionString) {
    return { ...EMPTY, error: "Falta la variable DASHBOARD_DATABASE_URL en la configuración del despliegue." };
  }
  pool ??= new Pool({ connectionString, max: 2, ssl: { rejectUnauthorized: false } });

  try {
    const { rows } = await pool.query<{ key: string; data: unknown; updated_at: Date }>(
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
      error: null,
    };
  } catch (err) {
    // Sin detalles de conexión en pantalla: el mensaje de pg puede incluir el host o el usuario.
    console.error("dashboard: no se pudo leer dashboard_snapshots", err);
    return { ...EMPTY, error: "No se pudo conectar a la base de datos. Revisa DASHBOARD_DATABASE_URL." };
  }
}
