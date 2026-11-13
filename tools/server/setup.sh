#!/usr/bin/env bash
# Run on the server, inside the app folder:  bash tools/server/setup.sh
# Installs Docker if needed, creates .env (password + address) the first time, then starts the app. Safe to run again to update.
set -e
cd "$(dirname "$0")/../.."
# Docker may be pre-installed (some hosts do) but without the "compose" part: install/complete it when anything is missing
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true
mkdir -p data
if [ -f ssdeal-data.zip ] && [ ! -f data/ssdeal.db ]; then mv ssdeal-data.zip data/import.zip; echo "Your data from the PC will be imported on first start."; fi
if [ ! -f .env ]; then
  PW="${SSDEAL_PASSWORD:-}"
  if [ -z "$PW" ]; then
    read -r -s -p "Choose a password for the app (at least 8 characters, empty = make one for me): " PW; echo
    if [ -z "$PW" ]; then PW="$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 16)"; echo "Your password: $PW   (write it down)"; fi
  fi
  if [ ${#PW} -lt 8 ]; then echo "Password must be at least 8 characters."; exit 1; fi
  DOM="${DOMAIN:-}"
  if [ -z "$DOM" ]; then
    IP="$(curl -4 -fsS https://api.ipify.org || true)"
    [ -n "$IP" ] || { echo "Could not find this server's public IP; run again with DOMAIN=your.domain bash tools/server/setup.sh"; exit 1; }
    DOM="$(echo "$IP" | tr . -).sslip.io"      # free name that points at this IP (sslip.io); use your own domain if you have one
  fi
  printf 'DOMAIN=%s\nSSDEAL_PASSWORD=%s\nSSDEAL_ADMIN_USER=%s\nTZ=%s\n' "$DOM" "$PW" "${SSDEAL_ADMIN_USER:-admin}" "${TZ:-Europe/Riga}" > .env
  chmod 600 .env
fi
grep -q '^SSDEAL_ADMIN_USER=' .env || echo 'SSDEAL_ADMIN_USER=admin' >> .env
docker compose up -d --build
. ./.env
echo
echo "Done. Open  https://$DOMAIN  on your phone or PC and log in as $SSDEAL_ADMIN_USER. Invite friends from Settings -> Phone -> Manage users."
echo "(The first start can take a minute while the HTTPS certificate is made.)"
