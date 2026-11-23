#!/usr/bin/env bash
# Polls the server over ssh for open local-step requests (`sf-status local pending`)
# and exits when there is one, so a chat session started with run_in_background wakes up.
# Usage: local-watch.sh <ssh-target> <project>
# Prints the pending request lines (JSON, one per line) on stdout when it exits 10.
# Exit code: 10 new step, 11 ssh or remote failure (one line on stderr),
#            12 maximum duration reached, 2 usage error. Never exits 0.
# Environment: SF_LOCAL_WATCH_INTERVAL (seconds, default 120),
#   SF_LOCAL_WATCH_MAX_SECONDS (default 28800), SF_LOCAL_WATCH_SSH (default ssh),
#   SF_LOCAL_WATCH_REMOTE (default sf-status),
#   SF_LOCAL_WATCH_SSH_TIMEOUT (whole seconds per ssh call, default 90; a call
#   that takes longer is killed and the watcher exits 11).
set -u

usage() {
  echo "usage: local-watch.sh <ssh-target> <project>" >&2
  exit 2
}

[ "$#" -eq 2 ] || usage
target="$1"
project="$2"
nl=$'\n'
case "$target" in ''|-*|*"$nl"*) usage ;; esac
re='^[a-z0-9]+(-[a-z0-9]+)*$'
case "$project" in *"$nl"*) usage ;; esac
[[ $project =~ $re ]] || usage

interval="${SF_LOCAL_WATCH_INTERVAL:-120}"
max="${SF_LOCAL_WATCH_MAX_SECONDS:-28800}"
ssh_cmd="${SF_LOCAL_WATCH_SSH:-ssh}"
remote="${SF_LOCAL_WATCH_REMOTE:-sf-status}"

ssh_timeout="${SF_LOCAL_WATCH_SSH_TIMEOUT:-90}"

tmp="$(mktemp -d "${TMPDIR:-/tmp}/local-watch.XXXXXX")" || { echo "local-watch.sh: cannot create temp dir" >&2; exit 11; }
pid=""
cleanup() {
  [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null
  rm -rf "$tmp"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

SECONDS=0
while true; do
  "$ssh_cmd" -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 -- \
    "$target" "$remote local pending --project $project" >"$tmp/out" 2>"$tmp/err" </dev/null &
  pid=$!
  start=$SECONDS
  while kill -0 "$pid" 2>/dev/null; do
    if [ $((SECONDS - start)) -ge "$ssh_timeout" ]; then
      kill "$pid" 2>/dev/null
      sleep 0.2
      kill -9 "$pid" 2>/dev/null
      wait "$pid" 2>/dev/null
      pid=""
      echo "local-watch.sh: ssh timed out after ${ssh_timeout} s" >&2
      exit 11
    fi
    sleep 0.1
  done
  wait "$pid"
  rc=$?
  pid=""
  if [ "$rc" -ne 0 ]; then
    echo "local-watch.sh: ssh failed (exit $rc)" >&2
    exit 11
  fi
  out="$(cat "$tmp/out")"
  if [ -n "$out" ]; then
    printf '%s\n' "$out"
    exit 10
  fi
  if [ "$SECONDS" -ge "$max" ]; then
    echo "local-watch.sh: maximum duration reached (${max}s)" >&2
    exit 12
  fi
  sleep "$interval"
done
