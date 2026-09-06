FROM python:3.11-slim

WORKDIR /app

COPY services/onvif-discovery/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY services/onvif-discovery/app.py .
COPY config/ /app/config/

EXPOSE 9002

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9002"]
