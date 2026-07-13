#!/usr/bin/env bash
set -euo pipefail

ROOT="${BC_ASSUMPTIONS_ROOT:-/opt/bc-assumptions-registry}"
VENV="${BC_ASSUMPTIONS_VENV:-$ROOT/.venv}"
REMOTE="${BC_ASSUMPTIONS_GIT_REMOTE:-origin}"
BRANCH="${BC_ASSUMPTIONS_GIT_BRANCH:-main}"
GIT_NAME="${BC_ASSUMPTIONS_GIT_NAME:-BC Assumptions Bot}"
GIT_EMAIL="${BC_ASSUMPTIONS_GIT_EMAIL:-bc-assumptions-bot@users.noreply.github.com}"

mkdir -p "$ROOT/state"
exec 9>"$ROOT/state/weekly.lock"
if ! flock -n 9; then
  echo "Another weekly registry run is already active" >&2
  exit 1
fi

cd "$ROOT"
git pull --ff-only "$REMOTE" "$BRANCH"

# A full source run evaluates collection status, configured coverage, and freshness.
# No Git-facing file is changed until that release gate passes.
"$VENV/bin/bc-assumptions" --root "$ROOT" run --all --no-export
"$VENV/bin/bc-assumptions" --root "$ROOT" export
"$VENV/bin/bc-assumptions" --root "$ROOT" validate-public

git add data/export site/data
if ! git diff --cached --quiet; then
  git -c user.name="$GIT_NAME" -c user.email="$GIT_EMAIL" \
    commit -m "data: weekly registry update $(date -u +%Y-%m-%d)"
fi

# Push even when this run produced no new diff. This retries a commit left local by
# an earlier transient push failure.
git push "$REMOTE" "$BRANCH"
