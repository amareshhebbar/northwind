#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

STATE=.state
mkdir -p "$STATE/pids" "$STATE/logs" "$STATE/versions"
PY="${PYTHON:-.venv/bin/python}"
MODE="${RUN_MODE:-single}"

need_venv() {
  if [ ! -x "$PY" ]; then
    echo "no virtualenv yet. Run: ./run.sh setup"
    exit 1
  fi
}

supported() {
  "$1" -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)' 2>/dev/null
}

pick_python() {
  for c in python3.12 python3.11 python3.13 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1 && supported "$c"; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

find_uv() {
  if command -v uv >/dev/null 2>&1; then command -v uv; return 0; fi
  [ -x "$HOME/.local/bin/uv" ] && { echo "$HOME/.local/bin/uv"; return 0; }
  [ -x "$HOME/.cargo/bin/uv" ] && { echo "$HOME/.cargo/bin/uv"; return 0; }
  return 1
}

cmd_setup() {
  if [ -x .venv/bin/python ] && ! supported .venv/bin/python; then
    echo "existing .venv uses $(.venv/bin/python --version 2>&1), which CrewAI and Google ADK do not support yet. Recreating it."
    rm -rf .venv
  fi
  local py uv
  if py="$(pick_python)"; then
    echo "using $("$py" --version) at $py"
    [ -x .venv/bin/python ] || "$py" -m venv .venv
    .venv/bin/python -m pip install -q --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
  elif uv="$(find_uv)"; then
    echo "no Python 3.10 to 3.13 found; uv will download Python 3.12 into .venv"
    [ -x .venv/bin/python ] || "$uv" venv --python 3.12 .venv
    "$uv" pip install --python .venv/bin/python -r requirements.txt
  else
    echo "This project needs Python 3.10 to 3.13 (CrewAI and Google ADK do not support 3.14 yet)."
    echo "Install one of these, then run ./run.sh setup again:"
    echo "  sudo dnf install python3.12"
    echo "  or: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi
  [ -f .env ] || cp .env.example .env
  .venv/bin/python tools/gen_data.py >/dev/null
  echo "setup done with $(.venv/bin/python --version). Edit .env and platform.yml, then: ./run.sh up all"
}

names_for() {
  local arg="${1:-all}"
  case "$arg" in
    all|lite|docker) "$PY" -m supportkit.cli names "$arg" ;;
    *) printf '%s\n' "$@" ;;
  esac
}

platform_up() {
  [ -f "$STATE/pids/platform.pid" ] && kill -0 "$(cat "$STATE/pids/platform.pid")" 2>/dev/null
}

is_up() {
  local name="$1" pidfile="$STATE/pids/$1.pid"
  if [ "$MODE" = single ] || [ -f "$STATE/pids/platform.pid" ]; then
    platform_up && grep -qx "$name" "$STATE/platform.services" 2>/dev/null
    return
  fi
  [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

start_one() {
  local name="$1"
  if is_up "$name"; then
    echo "$name already running"
    return 0
  fi
  nohup "$PY" -m supportkit.server "$name" >"$STATE/logs/$name.log" 2>&1 &
  echo $! >"$STATE/pids/$name.pid"
}

start_single() {
  local list="$1"
  if platform_up; then
    kill "$(cat "$STATE/pids/platform.pid")" 2>/dev/null || true
    for _ in $(seq 1 20); do platform_up || break; sleep 0.5; done
  fi
  echo "$list" | tr ' ' '\n' | sed '/^$/d' >"$STATE/platform.services"
  nohup "$PY" -m supportkit.multi $list >"$STATE/logs/platform.log" 2>&1 &
  echo $! >"$STATE/pids/platform.pid"
}

probe() {
  local name="$1" kind port path code
  read -r kind port path < <("$PY" -m supportkit.cli health "$name")
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port$path" 2>/dev/null || true)"
  if [ "$kind" = mcp ] || [ "$kind" = adk_app ]; then
    [ -n "$code" ] && [ "$code" != 000 ] && echo up && return 0
    echo down
    return 0
  fi
  if [ "$code" = 200 ]; then
    if curl -fsS "http://127.0.0.1:$port$path" 2>/dev/null | grep -q '"ok":true'; then echo up; else echo not_ready; fi
  else
    echo down
  fi
}

wait_one() {
  local name="$1"
  for _ in $(seq 1 180); do
    if ! is_up "$name"; then
      local log="$STATE/logs/$name.log"
      [ "$MODE" = single ] && log="$STATE/logs/platform.log"
      echo "x $name exited. Last log lines:"
      tail -n 8 "$log"
      return 1
    fi
    case "$(probe "$name")" in
      up|not_ready) return 0 ;;
    esac
    sleep 1
  done
  echo "x $name did not answer. See $STATE/logs/ for details"
  return 1
}

cmd_up() {
  need_venv
  local list
  list="$(names_for "$@")"
  if [ "$MODE" = single ]; then
    local merged
    merged="$( { cat "$STATE/platform.services" 2>/dev/null; echo "$list"; } | tr ' ' '\n' | sed '/^$/d' | awk '!seen[$0]++' | tr '\n' ' ')"
    platform_up || merged="$(echo "$list" | tr '\n' ' ')"
    start_single "$merged"
    echo "single process mode: $(echo "$merged" | wc -w) APIs in one Python process (RUN_MODE=multi for one process each)"
  else
    for n in $list; do start_one "$n"; done
  fi
  local failed=0
  for n in $list; do
    if wait_one "$n"; then
      local port state
      port="$("$PY" -m supportkit.cli port "$n")"
      state="$(probe "$n")"
      if [ "$state" = up ]; then
        echo "ok  $n :$port"
      else
        echo "!!  $n :$port is running but not ready: $(curl -s "http://127.0.0.1:$port/health")"
        failed=1
      fi
    else
      failed=1
    fi
  done
  return $failed
}

cmd_down() {
  need_venv
  if [ -f "$STATE/pids/platform.pid" ] && ! platform_up; then
    rm -f "$STATE/pids/platform.pid"
  fi
  if platform_up; then
    if [ "$#" -eq 0 ]; then
      kill "$(cat "$STATE/pids/platform.pid")" 2>/dev/null || true
      rm -f "$STATE/pids/platform.pid" "$STATE/platform.services"
      echo "stopped platform process"
    else
      local keep
      keep="$(grep -vxF -f <(names_for "$@") "$STATE/platform.services" | tr '\n' ' ' || true)"
      if [ -n "${keep// }" ]; then start_single "$keep"; echo "restarted platform without: $*"; else cmd_down; fi
    fi
  fi
  local list
  if [ "$#" -eq 0 ]; then list="$(ls "$STATE/pids" 2>/dev/null | sed 's/\.pid$//' | grep -vx -e platform -e fake_ollama || true)"; else list="$(names_for "$@")"; fi
  for n in $list; do
    if [ -f "$STATE/pids/$n.pid" ] && kill -0 "$(cat "$STATE/pids/$n.pid")" 2>/dev/null; then
      kill "$(cat "$STATE/pids/$n.pid")" 2>/dev/null || true
      echo "stopped $n"
    fi
    rm -f "$STATE/pids/$n.pid"
  done
}

cmd_status() {
  need_venv
  printf '%-18s %-6s %-20s %-9s %-8s %s\n' service port flow store version health
  "$PY" -m supportkit.cli list | while read -r name port flow store mix; do
    local ver health
    ver="$(cat "$STATE/versions/$name" 2>/dev/null || cat .active_version 2>/dev/null || echo v1)"
    if is_up "$name"; then health="$(probe "$name")"; else health=down; fi
    printf '%-18s %-6s %-20s %-9s %-8s %s\n' "$name" "$port" "$flow" "$store" "$ver" "$health"
  done
}

cmd_logs() {
  if [ -f "$STATE/logs/$1.log" ]; then tail -n "${2:-40}" "$STATE/logs/$1.log"; else tail -n "${2:-40}" "$STATE/logs/platform.log"; fi
}

cmd_reindex() {
  need_venv
  for n in $(names_for "${@:-all}"); do
    case "$n" in gateway|support_tools|concierge) continue ;; esac
    port="$("$PY" -m supportkit.cli port "$n")"
    echo "$n: $(curl -fsS -X POST "http://127.0.0.1:$port/admin/reindex")"
  done
}

case "${1:-help}" in
  setup) cmd_setup ;;
  up) shift; cmd_up "${@:-all}" ;;
  down) shift; cmd_down "$@" ;;
  restart)
    shift
    if [ "$MODE" = single ]; then
      current="$(cat "$STATE/platform.services" 2>/dev/null | tr '\n' ' ')"
      cmd_down
      if [ -n "${current// }" ]; then cmd_up $current; else cmd_up "${@:-all}"; fi
    else
      cmd_down "$@"; cmd_up "${@:-all}"
    fi
    ;;
  status) cmd_status ;;
  logs) shift; cmd_logs "$@" ;;
  reindex) shift; cmd_reindex "$@" ;;
  list) need_venv; "$PY" -m supportkit.cli list ;;
  fake-ollama)
    need_venv
    nohup "$PY" -m supportkit.fake_ollama --port "${2:-11435}" >"$STATE/logs/fake_ollama.log" 2>&1 &
    echo $! >"$STATE/pids/fake_ollama.pid"
    echo "fake Ollama on http://127.0.0.1:${2:-11435}. Set OLLAMA_HOST=http://127.0.0.1:${2:-11435} in .env and ./run.sh restart"
    ;;
  *)
    cat <<'H'
usage: ./run.sh <command>

  setup                  create .venv, install requirements, copy .env.example to .env
  up [all|lite|docker|name ...]   start services (lite = no docker databases)
                         RUN_MODE=single (default) hosts every API on its own port in one Python process
                         RUN_MODE=multi starts one Python process per API
  down [name ...]        stop services
  restart [name ...]
  status                 table of every service
  logs <name> [lines]
  reindex [name ...]     reload policy and records into each store
  list                   services with flow, store and agent mix
  fake-ollama [port]     start a local server that speaks the Ollama and OpenAI APIs with scripted answers,
                         so every framework's native client can run with no model installed
H
    ;;
esac