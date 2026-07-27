FROM python:3.13-slim

WORKDIR /app

# Dependencies
COPY dashboard-v2/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# FastAPI via Uvicorn
EXPOSE 3000

CMD ["uvicorn", "dashboard-v2.main:app", "--host", "0.0.0.0", "--port", "3000"]