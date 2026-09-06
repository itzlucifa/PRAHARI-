FROM python:3.11-slim

WORKDIR /app

COPY services/api-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY services/api-gateway/app.py .

EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
