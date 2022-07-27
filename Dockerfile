FROM python:3.10-alpine3.16

WORKDIR /usr/src

RUN apk add --no-cache smartmontools \
    && pip install prometheus_client \
    # remove temporary files
    && rm -rf /root/.cache/ \
    && find / -name '*.pyc' -delete

COPY ./smartprom.py /smartprom.py

EXPOSE 9902
ENTRYPOINT ["/usr/local/bin/python", "-u", "/smartprom.py"]

# HELP
# docker build -t matusnovak/prometheus-smartctl:test .
