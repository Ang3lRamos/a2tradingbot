# Imagen única para el bot y el dashboard.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADEBOT_SETTINGS=/app/config/settings.toml

# Claude Code CLI: el analista IA usa tu suscripción vía `claude -p`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
    && npm install -g @anthropic-ai/claude-code@2.1.319 \
    && apt-get purge -y npm && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* /root/.npm

RUN useradd --create-home bot
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[dashboard]"
COPY config ./config
COPY dashboard ./dashboard

USER bot
CMD ["python", "-m", "tradebot.run"]
