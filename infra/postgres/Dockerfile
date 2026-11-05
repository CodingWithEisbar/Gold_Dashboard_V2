FROM postgres:18.6-alpine
USER root
# The service always starts non-root; unused gosu carries an obsolete embedded Go runtime.
RUN apk upgrade --no-cache && rm -f /usr/local/bin/gosu
USER 70:70
