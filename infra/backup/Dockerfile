FROM postgres:18.6-alpine
USER root
RUN apk upgrade --no-cache && apk add --no-cache aws-cli && rm -f /usr/local/bin/gosu
COPY infra/backup/backup.sh /usr/local/bin/gold-backup
RUN chmod 0555 /usr/local/bin/gold-backup
USER 70:70
ENTRYPOINT []
CMD ["sleep", "infinity"]
