FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir --timeout 300 paho-mqtt opencv-python-headless numpy

COPY shared/ /app/shared/
COPY services/adapter_detection/adapter.py .
COPY test_feeds/ /app/test_feeds/

EXPOSE 8080

CMD ["python", "adapter.py"]
