FROM python:3.11-slim

WORKDIR /app

COPY services/case-file/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY services/case-file/app.py .
COPY config/ /app/config/
COPY test_feeds/ /app/test_feeds/

EXPOSE 9000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
