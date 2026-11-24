#!/bin/bash
# Generates a self-signed TLS certificate for LOCAL DEVELOPMENT ONLY.
# In production, use a CA-issued certificate (e.g. Let's Encrypt via certbot):
#   sudo certbot certonly --standalone -d airport.example.com
set -euo pipefail

CERT_DIR="$(dirname "$0")/ssl"
mkdir -p "$CERT_DIR"

openssl req -x509 -newkey rsa:4096 -sha256 -days 365 -nodes \
  -keyout "$CERT_DIR/server.key" \
  -out "$CERT_DIR/server.crt" \
  -subj "/C=US/ST=Dev/L=Dev/O=Save Flight/CN=localhost"

echo "Self-signed dev certificate written to $CERT_DIR"
