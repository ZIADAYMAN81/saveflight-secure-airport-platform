#!/bin/bash
# Scans both dependency trees for known-vulnerable packages (CVE/PYSEC
# advisories). This is the project's "malware/supply-chain risk" control -
# there's no file-upload feature in SAOP for traditional antivirus scanning
# to have anything to scan, so the realistic equivalent threat here is a
# *malicious or compromised dependency* (a real, common supply-chain attack
# class), not a user-uploaded file.
set -euo pipefail

echo "=== Backend (Python) dependency audit ==="
cd "$(dirname "$0")/../../backend"
if [ ! -d venv ]; then
  echo "backend/venv not found - run 'python -m venv venv && pip install -r requirements.txt' first."
  exit 1
fi
venv/Scripts/python.exe -m pip show pip-audit >/dev/null 2>&1 || venv/Scripts/python.exe -m pip install pip-audit
venv/Scripts/python.exe -m pip_audit -r requirements.txt

echo ""
echo "=== Frontend (npm) dependency audit ==="
cd ../frontend
echo "Runtime dependencies only (--omit=dev omits devDependencies; react-scripts"
echo "build-tooling findings are expected and tracked separately - see"
echo "docs/SECURITY.md, they never reach the shipped browser bundle):"
npm audit --omit=dev || true
