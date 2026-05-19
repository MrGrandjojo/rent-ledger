FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Run as a non-root user. UID 1000 keeps the bind-mounted uploads/ writable
# without requiring `chmod 777` on the host directory.
RUN groupadd --gid 1000 app && \
    useradd  --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin app && \
    mkdir -p /app/uploads && chown -R app:app /app
USER app

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
