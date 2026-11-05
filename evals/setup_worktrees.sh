#!/usr/bin/env bash
# Instructor: make the stage branches available to evals/run.py --stage N.
# Creates .worktrees/stage-2 and .worktrees/stage-3 (gitignored) at the branch tips.
set -euo pipefail
cd "$(dirname "$0")/.."
for n in 2 3; do
  wt=.worktrees/stage-$n
  if [ -d "$wt" ]; then git -C "$wt" checkout -q --detach "stage-$n"; else git worktree add -q --detach "$wt" "stage-$n"; fi
  git -C "$wt" rev-parse --short HEAD > "$wt/COMMIT"
  echo "$wt -> $(cat "$wt/COMMIT")"
done
