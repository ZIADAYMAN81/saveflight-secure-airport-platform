#!/bin/bash

ufw default deny incoming
ufw default allow outgoing
ufw limit 22/tcp comment 'SSH access'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw allow from 127.0.0.1 to any port 5432 comment 'Postgres local access'
ufw enable
ufw status verbose
