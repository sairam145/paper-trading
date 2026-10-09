#!/usr/bin/env bash
# restore: copy files from the `state` branch into ./state
# save:    force-push ./state (db + report + last 2000 log lines) as a single commit on `state`
set -euo pipefail
cmd=${1:?restore|save}
mkdir -p state
git config user.name "paper-trader-bot"
git config user.email "paper-trader-bot@users.noreply.github.com"
if [ "$cmd" = restore ]; then
  if git fetch -q origin state 2>/dev/null; then
    git --work-tree=state checkout FETCH_HEAD -- . && git reset -q
    echo "restored: $(ls state | tr '\n' ' ')"
  else
    echo "no state branch yet - first run starts fresh"
  fi
elif [ "$cmd" = save ]; then
  [ -f state/live.log ] && tail -n 2000 state/live.log > state/live.tmp && mv state/live.tmp state/live.log
  tmp=$(mktemp -d)
  cp -r state/. "$tmp"/
  rm -rf "$tmp"/replay_models "$tmp"/replay.db
  # build the commit inside this repo (keeps the checkout's push credentials), no history kept
  export GIT_INDEX_FILE="$tmp.index"
  git --work-tree="$tmp" add -A .
  commit=$(git commit-tree "$(git write-tree)" -m "state $(date -u +%Y-%m-%dT%H:%MZ)")
  unset GIT_INDEX_FILE
  git push -qf origin "$commit:refs/heads/state"
  echo "state saved"
fi
