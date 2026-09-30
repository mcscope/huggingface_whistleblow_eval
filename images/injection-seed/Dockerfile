FROM python:3.12-alpine
RUN apk add --no-cache curl
COPY seed.sh /seed.sh
RUN chmod +x /seed.sh
ENTRYPOINT ["/seed.sh"]
