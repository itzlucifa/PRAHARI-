FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir --timeout 300 fastapi uvicorn paho-mqtt qdrant-client psycopg2-binary

COPY shared/ /app/shared/
COPY services/fusion-service/app.py .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
