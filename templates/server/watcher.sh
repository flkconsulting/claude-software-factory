#!/usr/bin/env bash
# Waits until a time of day, checks a precondition (a command), then starts a strand.
# Otherwise leaves a warning notice for the human (sf-status launch, sf-status notice --level warning).
# usage: watcher.sh <HH:MM> <project> <short> <model> <worktree> <topic> <precondition command...>
set -e

if [ "$#" -lt 7 ]; then
  echo "usage: watcher.sh <HH:MM> <project> <short> <model> <worktree> <topic> <precondition command...>" >&2
  exit 2
fi
at="$1"; project="$2"; short="$3"; model="$4"; worktree="$5"; topic="$6"
shift 6
SF_STATUS="${SF_STATUS:-<plugin-dir>/scripts/bin/sf-status}"
poll="${SF_WATCHER_POLL:-20}"

# Start once the time of day has been reached (also when started late, same day).
# SF_WATCHER_NOW (HH:MM) replaces the clock; used by tests.
now() { echo "${SF_WATCHER_NOW:-$(date +%H:%M)}"; }
while [[ "$(now)" < "$at" ]]; do
  sleep "$poll"
done

if "$@"; then
  "$SF_STATUS" launch --project "$project" --short "$short" --model "$model" --worktree "$worktree" --topic "$topic"
else
  "$SF_STATUS" notice --project "$project" --strand "$short" --level warning \
    --title "precondition not met" "Strand $short was not started: its precondition failed at $at."
fi
