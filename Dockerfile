FROM alpine:3.12

WORKDIR /usr/src

RUN apk update; \
    apk add --no-cache python3 py3-pip smartmontools; \
    python3 -m pip install prometheus_client;

ADD smartprom.py .

EXPOSE 9902
ENTRYPOINT "./smartprom.py"
