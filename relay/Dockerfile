FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin relay

# The Docker build context is this relay/ directory.  Keeping it self-contained
# prevents the app repository and any local Streamlit secret file from being
# copied into the Cloud Run image.
COPY . /app/relay
RUN chown -R relay:relay /app

USER relay

EXPOSE 8080

# One worker is intentional: the default nonce cache is process-local.
CMD ["sh", "-c", "uvicorn relay.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers"]
