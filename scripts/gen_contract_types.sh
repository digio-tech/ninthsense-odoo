#!/usr/bin/env bash
# Regenerate ninthsense/core/contract_types.py from the vendored
# portal schemas. Only the completion types are used; the header pins the
# digests of both schemas so a schema change shows up in review.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA_DIR="$ROOT/ninthsense/schemas"
OUT="$ROOT/ninthsense/core/contract_types.py"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

REQUEST_SHA="$(shasum -a 256 "$SCHEMA_DIR/request.schema.json" | awk '{print $1}')"
COMPLETION_SHA="$(shasum -a 256 "$SCHEMA_DIR/completion.schema.json" | awk '{print $1}')"

uvx --from datamodel-code-generator datamodel-codegen \
  --input-file-type jsonschema \
  --output-model-type dataclasses.dataclass \
  --target-python-version 3.12 \
  --input "$SCHEMA_DIR/completion.schema.json" \
  --output "$TMP_DIR/completion_types.py"

# The completion module names its step class Step; the core imports CompletionStep.
python3 -c "
import re, sys
path = sys.argv[1]
text = open(path).read()
open(path, 'w').write(re.sub(r'\bStep\b', 'CompletionStep', text))
" "$TMP_DIR/completion_types.py"

{
  echo "# request.schema.json sha256=$REQUEST_SHA"
  echo "# completion.schema.json sha256=$COMPLETION_SHA"
  echo
  echo "from dataclasses import dataclass"
  echo "from enum import Enum"
  echo "from typing import Any"
  echo
  sed -e '1,/^$/d' "$TMP_DIR/completion_types.py" \
    | grep -vE '^(from __future__ import annotations|from dataclasses import dataclass|from enum import Enum|from typing import Any)$'
} > "$OUT"

uvx ruff format "$OUT"
uvx ruff check --fix "$OUT" || true
echo "wrote $OUT"
