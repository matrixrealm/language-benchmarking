FROM python:3.14.0-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
ENV WORKERS=1
CMD ["sh", "-c", "exec uvicorn app:application --host 0.0.0.0 --port 8080 --workers ${WORKERS} --no-access-log"]
