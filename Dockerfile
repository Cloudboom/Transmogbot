FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata tini sqlite3 \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /usr/sbin/nologin appuser \
 && mkdir -p /data /bot \
 && chown -R appuser:appuser /data /bot

WORKDIR /bot

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "bot.py"]
