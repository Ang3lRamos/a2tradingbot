"use server";

// Acciones del panel de control. Cada una se puede llamar con un POST directo, así que todas
// verifican la sesión. Solo dejan órdenes pendientes: el bot las valida otra vez y las ejecuta.

import { updateTag } from "next/cache";

import { enqueue, MAX_PENDING, pendingCount, recentCommands } from "@/lib/control-db";
import { DASHBOARD_TAG } from "@/lib/data";
import { controlsConfigured, endSession, hasSession, passwordMatches, startSession } from "@/lib/session";
import type { ActionResult, Command, ControlState } from "@/lib/types";

const COINS = ["BTC", "ETH", "SOL"];
const BOTS = ["rupturas", "tendencia"];

export async function login(_: ActionResult | null, form: FormData): Promise<ActionResult> {
  if (!controlsConfigured()) return { ok: false, error: "Los controles no están configurados en este despliegue." };
  if (!passwordMatches(String(form.get("password") ?? ""))) {
    await new Promise((resolve) => setTimeout(resolve, 1500)); // frena los intentos a ciegas
    return { ok: false, error: "Contraseña incorrecta." };
  }
  await startSession();
  return { ok: true };
}

export async function logout(): Promise<void> {
  await endSession();
}

export async function getControlState(): Promise<ControlState> {
  if (!(await hasSession())) return { authed: false, configured: controlsConfigured() };
  return { authed: true, configured: true, commands: await recentCommands() };
}

async function send(kind: Command["kind"], payload: Record<string, unknown>): Promise<ActionResult> {
  if (!(await hasSession())) return { ok: false, error: "La sesión venció: vuelve a entrar." };
  try {
    if ((await pendingCount()) >= MAX_PENDING) {
      return { ok: false, error: "Hay demasiadas órdenes esperando. ¿Está corriendo el bot?" };
    }
    await enqueue(kind, payload);
    return { ok: true };
  } catch (err) {
    console.error("control: no se pudo crear la orden", err);
    return { ok: false, error: "No se pudo guardar la orden en la base de datos." };
  }
}

export async function setAggressiveness(bot: string, value: number): Promise<ActionResult> {
  if (!BOTS.includes(bot) || !(value >= 0.25 && value <= 2) || (value * 4) % 1 !== 0) {
    return { ok: false, error: "Agresividad inválida." };
  }
  return send("agresividad", { bot, valor: value });
}

export async function openManual(input: { coin: string; side: string; riskPct: number; stopPct: number }): Promise<ActionResult> {
  const { coin, side, riskPct, stopPct } = input;
  if (!COINS.includes(coin) || (side !== "long" && side !== "short")) return { ok: false, error: "Moneda o lado inválido." };
  if (!(riskPct >= 0.05 && riskPct <= 2)) return { ok: false, error: "El riesgo debe estar entre 0,05% y 2%." };
  if (!(stopPct >= 0.2 && stopPct <= 20)) return { ok: false, error: "El stop debe estar entre 0,2% y 20%." };
  return send("abrir", { simbolo: coin, lado: side, riesgo_pct: riskPct, stop_pct: stopPct });
}

export async function closeManual(positionId: number): Promise<ActionResult> {
  if (!Number.isInteger(positionId) || positionId <= 0) return { ok: false, error: "Posición inválida." };
  return send("cerrar", { posicion_id: positionId });
}

/** Tras una orden ejecutada, el bot ya republicó: se descarta la copia en caché del dashboard. */
export async function refreshDashboard(): Promise<void> {
  if (await hasSession()) updateTag(DASHBOARD_TAG);
}
