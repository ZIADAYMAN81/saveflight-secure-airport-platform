# Adds a self-signed TLS server certificate (for LOCAL DEVELOPMENT ONLY - use
# a CA-issued cert in production) and a custom pg_hba.conf that requires TLS
# for all network connections, closing the gap where backend<->postgres
# traffic previously ran in plaintext (see docs/SECURITY.md).
FROM postgres:15-alpine

RUN apk add --no-cache openssl \
    && openssl req -x509 -newkey rsa:4096 -sha256 -days 365 -nodes \
         -keyout /var/lib/postgresql/server.key \
         -out /var/lib/postgresql/server.crt \
         -subj "/C=US/ST=Dev/L=Dev/O=Save Flight/CN=postgres" \
    && chown postgres:postgres /var/lib/postgresql/server.key /var/lib/postgresql/server.crt \
    && chmod 600 /var/lib/postgresql/server.key \
    && chmod 644 /var/lib/postgresql/server.crt

COPY pg_hba.conf /etc/postgresql/pg_hba.conf
RUN chown postgres:postgres /etc/postgresql/pg_hba.conf
