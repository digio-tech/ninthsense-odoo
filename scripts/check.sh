#!/usr/bin/env bash
# The single gate for ninthsense_onboarding: lint, dependency audit, core unit
# tests and the Odoo test suite on a throwaway database. CI runs this too.
#
# ODOO_DIR  Odoo 20 checkout holding odoo-bin and a .venv (default: this repo's parent)
# ODOO_CONF optional Odoo config for database connection settings
# HTTP_PORT optional port for the test server (default: a free port)
# PG_BIN    optional directory of the Postgres client tools
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ODOO_DIR="${ODOO_DIR:-$(cd "$ROOT/.." && pwd)}"
VENV_PYTHON="${VENV_PYTHON:-$ODOO_DIR/.venv/bin/python}"
ODOO_BIN="${ODOO_BIN:-$ODOO_DIR/odoo-bin}"
ADDONS_PATH="$ODOO_DIR/addons,$ROOT"
# The browser and HTTP tests talk to the test server on this port, so it must
# never be the port of a running Odoo; otherwise they would hit that server.
HTTP_PORT="${HTTP_PORT:-$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')}"
ODOO_ARGS=(--addons-path="$ADDONS_PATH")
[ -n "${ODOO_CONF:-}" ] && ODOO_ARGS=(-c "$ODOO_CONF" "${ODOO_ARGS[@]}")

_pg_tool() {
    if [ -n "${PG_BIN:-}" ] && [ -x "$PG_BIN/$1" ]; then
        echo "$PG_BIN/$1"
        return
    fi
    command -v "$1"
}
DROPDB="$(_pg_tool dropdb)"

DB="ninthsense_onboarding_test_$(date +%s)"
LOG_FILE="$(mktemp -t ninthsense_onboarding_check_XXXXXX.log)"
status=0

cleanup() {
    # Odoo's own drop also removes the filestore; dropdb alone leaves it on disk.
    "$VENV_PYTHON" "$ODOO_BIN" db "${ODOO_ARGS[@]}" drop "$DB" >/dev/null 2>&1 \
        || "$DROPDB" --if-exists "$DB" >/dev/null 2>&1 || true
    rm -f "$LOG_FILE"
}
trap cleanup EXIT

cd "$ROOT"

echo "== installing test dependencies into the venv =="
uv pip install --python "$VENV_PYTHON" -r scripts/requirements-dev.txt || status=1

echo "== ruff check =="
uvx ruff check . || status=1

echo "== ruff format --check =="
uvx ruff format --check . || status=1

echo "== pip-audit against the addon's dependencies =="
FREEZE_FILE="$(mktemp -t ninthsense_onboarding_freeze_XXXXXX.txt)"
uv pip freeze --python "$VENV_PYTHON" > "$FREEZE_FILE"
AUDIT_FILE="$(mktemp -t ninthsense_onboarding_audit_XXXXXX.txt)"
: > "$AUDIT_FILE"
while IFS= read -r package; do
    [ -z "$package" ] && continue
    grep -i "^${package}==" "$FREEZE_FILE" >> "$AUDIT_FILE" || true
done < scripts/requirements-dev.txt
uvx pip-audit -r "$AUDIT_FILE" || status=1
rm -f "$FREEZE_FILE" "$AUDIT_FILE"

echo "== core unit tests (odoo blocked) =="
(cd ninthsense_onboarding && "$VENV_PYTHON" -m unittest discover -s core/tests -t .) || status=1

echo "== odoo tests on a throwaway database =="
"$VENV_PYTHON" "$ODOO_BIN" "${ODOO_ARGS[@]}" \
    -d "$DB" --db-filter="^${DB}\$" --http-port="$HTTP_PORT" -i ninthsense_onboarding \
    --test-tags /ninthsense_onboarding --stop-after-init \
    2>&1 | tee "$LOG_FILE"

if grep -qE ': (FAIL|ERROR): ' "$LOG_FILE"; then
    echo "== odoo test log contains FAIL or ERROR =="
    status=1
fi
if ! grep -qE '0 failed, 0 error\(s\) of [1-9][0-9]* tests' "$LOG_FILE"; then
    echo "== odoo test summary missing or not clean =="
    status=1
fi
if grep -qE ': skipped |SkipTest' "$LOG_FILE"; then
    echo "== odoo test log contains a skipped test =="
    status=1
fi

exit "$status"
