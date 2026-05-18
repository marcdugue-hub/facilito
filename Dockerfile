FROM python:3.11-slim

# System deps for weasyprint (PDF) + healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-liberation \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# data/ sera monté en volume — on crée le dossier pour éviter des erreurs au démarrage
RUN mkdir -p /app/data

EXPOSE 8000

ENV APP_HOST=0.0.0.0 \
    APP_PORT=8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["python", "-m", "Agent.Main.main", "--openai"]
