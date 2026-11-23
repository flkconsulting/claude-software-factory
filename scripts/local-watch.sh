#!/usr/bin/env bash
# Polls the server over ssh for open local-step requests (`sf-status local pending`)
# and exits when there is one, so a chat session started with run_in_background wakes up.
# Usage: local-watch.sh <ssh-target> <project>
# Prints the pending request lines (JSON, one per line) on stdout when it exits 10.
# Exit code: 10 new step, 11 ssh or remote failure (one line on stderr),
#            12 maximum duration reached, 2 usage error. Never exits 0.
# Environment: SF_LOCAL_WATCH_INTERVAL (seconds, default 120),
#   SF_LOCAL_WATCH_MAX_SECONDS (default 28800), SF_LOCAL_WATCH_SSH (default ssh),
#   SF_LOCAL_WATCH_REMOTE (default sf-status).
set -u

usage() {
  echo "usage: local-watch.sh <ssh-target> <project>" >&2
  exit 2
}

[ "$#" -eq 2 ] || usage
target="$1"
project="$2"
case "$target" in ''|-*) usage ;; esac
if ! printf '%s' "$project" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$'; then
  usage
fi

interval="${SF_LOCAL_WATCH_INTERVAL:-120}"
max="${SF_LOCAL_WATCH_MAX_SECONDS:-28800}"
ssh_cmd="${SF_LOCAL_WATCH_SSH:-ssh}"
remote="${SF_LOCAL_WATCH_REMOTE:-sf-status}"

SECONDS=0
while true; do
  out="$("$ssh_cmd" -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 -- \
    "$target" "$remote local pending --project $project")"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "local-watch.sh: ssh failed (exit $rc)" >&2
    exit 11
  fi
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
