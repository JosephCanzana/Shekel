# ─────────────────────────────────────────────
# Stage 1: Build Tailwind CSS
# ─────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

# Copy entire css folder so my_theme.css and input.css are both present
COPY app/static/css ./app/static/css
COPY app/templates ./app/templates

RUN npm run build


# ─────────────────────────────────────────────
# Stage 2: Production Python image
# ─────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

COPY . .

COPY --from=frontend-builder /app/app/static/css/output.css ./app/static/css/output.css

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

CMD ["gunicorn", "--workers=2", "--threads=2", "--bind=0.0.0.0:5000", "--timeout=120", "run:app"]