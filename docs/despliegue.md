# Despliegue en un VPS

El bot tiene que correr 24/7 para cumplir el criterio de 30 días seguidos en papel. En un PC se detiene cuando el equipo se apaga o suspende; un VPS pequeño con Docker lo resuelve.

## 1. Servidor

Un VPS Linux con 1 vCPU y 1-2 GB de RAM alcanza (Hetzner, DigitalOcean, Vultr, Contabo). Ubuntu 24.04. Instala Docker:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # cierra sesión y vuelve a entrar
```

## 2. Código y secretos

```bash
git clone https://github.com/Ang3lRamos/a2tradingbot.git && cd a2tradingbot
mkdir -p secrets && chmod 700 secrets
```

Desde tu PC, copia el `.env` y la llave privada sin pasar por GitHub:

```bash
scp .env usuario@IP_DEL_VPS:~/a2tradingbot/.env
scp C:/Users/angel/.keys/binance-demo/id_ed25519 usuario@IP_DEL_VPS:~/a2tradingbot/secrets/id_ed25519
```

En el VPS: `chmod 600 .env secrets/id_ed25519`.

## 3. Claude en el servidor

El analista usa tu suscripción. En tu PC, genera un token de larga duración:

```bash
claude setup-token
```

Agrégalo al `.env` del VPS como `CLAUDE_CODE_OAUTH_TOKEN=...`. Comparte los límites de uso de tu plan; el tope diario del bot (`daily_call_limit`) deja margen para tu uso normal.

## 4. Alertas por Telegram

1. En Telegram, abre **@BotFather**, envía `/newbot` y sigue los pasos. Te da un token.
2. Envíale cualquier mensaje a tu bot nuevo.
3. Abre `https://api.telegram.org/bot<TOKEN>/getUpdates` en el navegador y copia el número de `"chat":{"id": ...}`.
4. En `.env`: `TELEGRAM_BOT_TOKEN=...` y `TELEGRAM_CHAT_ID=...`.

Llegan avisos de aperturas, stops movidos o faltantes, pérdida diaria, kill switch, desajustes de reconciliación y fallos del ciclo.

## 5. Arrancar

```bash
docker compose up -d --build
docker compose logs -f bot        # ver el bot
```

El bot corre un ciclo a los 2 minutos de cada hora (UTC) y se reinicia solo si el servidor se reinicia.

## 6. Ver el dashboard

El dashboard web (`web/`) se despliega en Vercel y lee los datos que el bot publica en Supabase. Ver la sección "Dashboard en Vercel" del README.

## Operación

| Acción | Comando |
|---|---|
| Ver logs | `docker compose logs -f bot` |
| Un ciclo manual | `docker compose run --rm bot python -m tradebot.run --once` |
| Reanudar tras kill switch (después de revisar) | `docker compose run --rm bot python -m tradebot.run --reanudar` |
| Actualizar el código | `git pull && docker compose up -d --build` |
| Detener | `docker compose down` |

Corre el bot en un solo lugar a la vez: si queda corriendo en tu PC y en el VPS, los dos operan la misma cuenta.
