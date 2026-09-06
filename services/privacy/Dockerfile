FROM python:3.11-slim

WORKDIR /app

COPY services/privacy/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY services/privacy/app.py .
COPY test_feeds/ /app/test_feeds/

EXPOSE 9001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9001"]
