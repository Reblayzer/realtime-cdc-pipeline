#!/usr/bin/env bash
# Registers the Debezium Postgres connector with Kafka Connect.
# Idempotent: if a connector with the same name already exists it gets replaced.
set -euo pipefail

CONNECT_URL="${CONNECT_URL:-http://localhost:8083}"
CONFIG_FILE="${CONFIG_FILE:-$(dirname "$0")/../debezium/register-postgres.json}"
NAME="$(jq -r .name "$CONFIG_FILE")"

echo "→ waiting for Kafka Connect at $CONNECT_URL ..."
for i in {1..60}; do
  if curl -fsS "$CONNECT_URL/" >/dev/null 2>&1; then
    echo "  Connect is up"
    break
  fi
  sleep 2
  if [[ $i -eq 60 ]]; then
    echo "✗ Connect did not become ready in 120s"
    exit 1
  fi
done

# PUT /connectors/{name}/config is idempotent: creates or replaces.
echo "→ registering connector '$NAME' ..."
jq .config "$CONFIG_FILE" \
  | curl -fsS -X PUT \
      -H "Content-Type: application/json" \
      --data @- \
      "$CONNECT_URL/connectors/$NAME/config" \
  | jq -r '.name + " → " + .config["connector.class"]'

echo "→ status:"
sleep 2
curl -fsS "$CONNECT_URL/connectors/$NAME/status" | jq '{name, connector: .connector.state, tasks: [.tasks[] | {id, state}]}'
