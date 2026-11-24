-- Enables column-level encryption support (pgcrypto) used for defense-in-depth
-- alongside the application-layer AES-256/Fernet encryption in backend/src/security.py.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
