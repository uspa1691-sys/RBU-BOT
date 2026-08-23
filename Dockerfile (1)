FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# SQLite bazasi shu papkaga yoziladi (Fly volume shu yerga ulanadi)
RUN mkdir -p /data
ENV DB_PATH=/data/rbu.db

EXPOSE 8080

CMD ["python", "bot.py"]
