FROM python:3.13-slim-bookworm

WORKDIR /app

# Dependencies
COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# FastAPI via Uvicorn
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/health', timeout=3)"]

CMD ["uvicorn", "dashboard.main:app", "--host", "0.0.0.0", "--port", "3000"]
