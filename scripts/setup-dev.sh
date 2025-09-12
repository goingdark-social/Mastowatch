#!/usr/bin/env bash
set -euo pipefail

env_file=".env.development"
if [ -f .env.local ]; then
  env_file=".env.local"
fi

gen_file=".env.generated"
touch "$gen_file"
for key in API_KEY WEBHOOK_SECRET SESSION_SECRET_KEY; do
  if ! grep -q "^$key=" "$env_file" && ! grep -q "^$key=" "$gen_file"; then
    value=$(openssl rand -hex 32)
    echo "$key=$value" >> "$gen_file"
  fi
done

set -a
source "$env_file"
source "$gen_file"
set +a

docker compose up -d
