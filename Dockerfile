# BIND9 Web UI — container image (controls a local or remote `named`)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py \
    BIND_CONF_DIR=/etc/bind \
    RNDC_PORT=953

# rndc, named-checkzone/conf, dig, and curl for healthchecks
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bind9-utils bind9-dnsutils dnsutils curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/cache/bind /var/log/bind

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py bind_manager.py ./
COPY templates ./templates
COPY static ./static

# The UI must write /etc/bind and run rndc, so run as root inside the container.
# Point it at named with RNDC_HOST / mount /etc/bind when using the compose stack.
EXPOSE 5000

CMD ["python", "app.py"]
