import "server-only";

import { Pool } from "pg";

import type { Command } from "./types";

// Usuario dashboard_operator: solo puede insertar órdenes pendientes en `commands` y leer su estado
// (ver sql/007_controls.sql). El bot las valida y ejecuta; el dashboard nunca toca el exchange.
let pool: Pool | undefined;

function db(): Pool {
  const connectionString = process.env.DASHBOARD_OPERATOR_URL;
  if (!connectionString) throw new Error("Falta DASHBOARD_OPERATOR_URL");
  pool ??= new Pool({ connectionString, max: 2, ssl: { rejectUnauthorized: false } });
  return pool;
}

export const MAX_PENDING = 5;

export async function recentCommands(limit = 10): Promise<Command[]> {
  const { rows } = await db().query<Omit<Command, "created_at"> & { created_at: Date }>(
    "select id, kind, payload, status, result, created_at from commands order by id desc limit $1", [limit]);
  return rows.map((r) => ({ ...r, id: Number(r.id), created_at: r.created_at.toISOString() }));
}

export async function pendingCount(): Promise<number> {
  const { rows } = await db().query<{ n: string }>(
    "select count(*) as n from commands where status in ('pendiente', 'ejecutando')");
  return Number(rows[0].n);
}

export async function enqueue(kind: Command["kind"], payload: Record<string, unknown>): Promise<number> {
  const { rows } = await db().query<{ id: string }>(
    "insert into commands (kind, payload) values ($1, $2) returning id", [kind, JSON.stringify(payload)]);
  return Number(rows[0].id);
}
