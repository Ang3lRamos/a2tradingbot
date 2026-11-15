import "server-only";

import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

// Sesión del panel de control: cookie httpOnly con su vencimiento firmado (HMAC). Sin base de datos:
// cambiar CONTROL_SESSION_SECRET cierra todas las sesiones abiertas.
const COOKIE = "tb_control";
const TTL_SECONDS = 12 * 3600;

function secret(): string | undefined {
  const value = process.env.CONTROL_SESSION_SECRET;
  return value && value.length >= 32 ? value : undefined;
}

/** El despliegue tiene todo lo necesario para los controles. Si falta algo, el panel solo lo explica. */
export function controlsConfigured(): boolean {
  return Boolean(process.env.CONTROL_PASSWORD && secret() && process.env.DASHBOARD_OPERATOR_URL);
}

function sameBytes(a: Buffer, b: Buffer): boolean {
  return a.length === b.length && timingSafeEqual(a, b);
}

function sign(value: string): string {
  return createHmac("sha256", secret()!).update(value).digest("base64url");
}

export function passwordMatches(input: string): boolean {
  const expected = process.env.CONTROL_PASSWORD;
  if (!expected) return false;
  // Se comparan los hashes para que la comparación no dependa del largo de la contraseña.
  const hash = (text: string) => createHash("sha256").update(text).digest();
  return sameBytes(hash(input), hash(expected));
}

export async function startSession(): Promise<void> {
  const expires = String(Math.floor(Date.now() / 1000) + TTL_SECONDS);
  (await cookies()).set(COOKIE, `${expires}.${sign(expires)}`, {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict", path: "/", maxAge: TTL_SECONDS,
  });
}

export async function endSession(): Promise<void> {
  (await cookies()).delete(COOKIE);
}

export async function hasSession(): Promise<boolean> {
  if (!controlsConfigured()) return false;
  const value = (await cookies()).get(COOKIE)?.value;
  const [expires, signature] = value?.split(".") ?? [];
  if (!expires || !signature) return false;
  if (!sameBytes(Buffer.from(signature), Buffer.from(sign(expires)))) return false;
  return Number(expires) * 1000 > Date.now();
}
