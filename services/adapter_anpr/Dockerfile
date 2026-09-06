FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir --timeout 300 "torch>=2.2.0" --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --timeout 300 ultralytics easyocr opencv-python-headless paho-mqtt numpy filterpy

COPY shared/ /app/shared/
COPY services/adapter_anpr/adapter.py .
COPY test_feeds/ /app/test_feeds/

EXPOSE 8080

CMD ["python", "adapter.py"]
