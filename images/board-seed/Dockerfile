FROM python:3.12-alpine
RUN apk add --no-cache curl
COPY seed.py /seed.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
