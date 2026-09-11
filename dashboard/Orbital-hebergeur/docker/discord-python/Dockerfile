# Synkrone Discord runtime — Python 3.12 (registry.example.com/platform/discord-python:1.0)
FROM python:3.12-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -u 1000 -m bot

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY boot.sh /usr/local/bin/synkrone-boot
RUN chmod +x /usr/local/bin/synkrone-boot

USER 1000:1000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/synkrone-boot"]
