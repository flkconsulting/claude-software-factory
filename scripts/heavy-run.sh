#!/usr/bin/env bash
# Runs one heavy command (full test run, build, end-to-end run) while holding
# one of N slots, so only N heavy runs go at the same time on a shared machine.
# Slots are lock files <state>/heavy/slot-<n>.lock, taken with flock -n on fd 9.
# N = server.heavy_slots, <state> = server.state_dir (both from `sf-status config`).
# Waits until a slot is free and reports that once on stderr.
# Exit code: that of the command; 2 for usage errors or when flock is missing.
set -u

if [ "$#" -eq 0 ]; then
  echo "usage: heavy-run.sh <command> [args...]" >&2
  exit 2
fi
if ! command -v flock >/dev/null 2>&1; then
  echo "heavy-run.sh: flock not found (macOS: install util-linux, e.g. brew install util-linux)" >&2
  exit 2
fi

SELF="$(readlink -f "$0" 2>/dev/null || echo "$0")"
SF_STATUS="$(dirname "$SELF")/bin/sf-status"

slots="$("$SF_STATUS" config heavy_slots 2>/dev/null)"
state="$("$SF_STATUS" config state_dir 2>/dev/null)"
case "$slots" in ''|*[!0-9]*|0) slots=2 ;; esac
[ -n "$state" ] || state="$HOME/.claude/software-factory/server"
poll="${SF_HEAVY_POLL:-20}"

mkdir -p "$state/heavy" || { echo "heavy-run.sh: cannot create $state/heavy" >&2; exit 2; }

announced=0
while true; do
  n=1
  while [ "$n" -le "$slots" ]; do
    exec 9>"$state/heavy/slot-$n.lock"
    if flock -n 9; then
      # 9>&- keeps the lock out of the child: the slot is tied to this script
      # process alone, so a background process left behind by the command
      # cannot hold it after the command has ended.
      "$@" 9>&- <&0 &
      pid=$!
      # Forward TERM and INT to the child; the slot is released (script exit)
      # only after the child has really ended.
      trap 'kill -TERM "$pid" 2>/dev/null' TERM INT
      status=0
      while true; do
        wait "$pid"
        status=$?
        kill -0 "$pid" 2>/dev/null || break
      done
      exit "$status"
    fi
    exec 9>&-
    n=$((n + 1))
  done
  if [ "$announced" -eq 0 ]; then
    echo "waiting for a heavy-run slot" >&2
    announced=1
  fi
  sleep "$poll"
done
