FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LOG_FILE=/app/logs/bot.log \
    TZ=Asia/Tashkent \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# System deps: DejaVu fonts so matplotlib renders Cyrillic/Latin chart labels,
# and tzdata for correct timestamps.
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

RUN groupadd --gid 10001 fitnessbot \
    && useradd --uid 10001 --gid fitnessbot --create-home fitnessbot

COPY --chown=fitnessbot:fitnessbot . .

# Media/fonts and rotating logs are persisted via volumes.
RUN mkdir -p /app/logs /app/assets \
    && chown -R fitnessbot:fitnessbot /app/logs /app/assets
VOLUME ["/app/assets", "/app/logs"]

USER fitnessbot:fitnessbot
STOPSIGNAL SIGTERM
CMD ["python", "main.py"]
