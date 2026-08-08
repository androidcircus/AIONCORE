FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libvirt-dev \
    qemu-utils \
    genisoimage \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY tasks.py .

CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "--concurrency=1"]
