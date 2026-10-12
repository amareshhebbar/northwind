#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-.venv/bin/python}"
mkdir -p .state/versions

valid() {
  case "$1" in v1|v2|v3|v4|v5) return 0 ;; *) return 1 ;; esac
}

case "${1:-show}" in
  show)
    "$PY" -m supportkit.cli active
    ;;
  reset)
    rm -f .state/versions/*
    echo "per service overrides removed"
    "$PY" -m supportkit.cli active
    ;;
  v1|v2|v3|v4|v5)
    v="$1"
    shift
    if [ "$#" -eq 0 ]; then
      echo "$v" > .active_version
      rm -f .state/versions/*
      echo "all services now use $v"
    else
      for n in "$@"; do
        echo "$v" > ".state/versions/$n"
        echo "$n now uses $v"
      done
    fi
    "$PY" -m supportkit.cli active
    ;;
  *)
    echo "usage: ./switch.sh v1|v2|v3|v4|v5 [service ...] | show | reset"
    exit 1
    ;;
esac
