#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-.venv/bin/python}"
if [ "$#" -lt 2 ]; then
  echo 'usage: ./ask.sh <service> "<question>" [v1|v2|v3|v4|v5|all] [-v] [--raw]'
  exit 1
fi
service="$1"
question="$2"
shift 2
version=""
extra=()
for a in "$@"; do
  case "$a" in
    v1|v2|v3|v4|v5|all) version="$a" ;;
    *) extra+=("$a") ;;
  esac
done
args=("$service" "$question")
[ -n "$version" ] && args+=(--version "$version")
exec "$PY" -m supportkit.cli ask "${args[@]}" "${extra[@]}"
