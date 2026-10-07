#!/usr/bin/env bash
# Bring the plugin work (Phase 8 commit, PL0-PL7, review fixes) into this repo.
#
#   cd ~/Documents/Projects/multicam-studio
#   bash ~/Downloads/apply-plugin-work.sh ~/Downloads/multicam-plugins.bundle
#
# Safe: your uncommitted files (the Phase 8 copy) are stashed first, not deleted.
set -euo pipefail

BUNDLE="${1:-multicam-plugins.bundle}"
[ -d .git ] || { echo "Run this from the multicam-studio repo folder."; exit 1; }
[ -f "$BUNDLE" ] || { echo "Bundle not found: $BUNDLE"; exit 1; }

echo "== 1/5 checking the bundle"
git bundle verify "$BUNDLE"
[ "$(git rev-parse HEAD)" = "$(git rev-parse 351ade4)" ] || {
  echo "Expected HEAD at 351ade4 (Phase 6+7). Found $(git log --oneline -1). Stop."; exit 1; }

# Keep the bundle and this script out of the stash.
TMPB="$(mktemp -d)/multicam-plugins.bundle"; cp "$BUNDLE" "$TMPB"; BUNDLE="$TMPB"
echo "== 2/5 stashing uncommitted files (Phase 8 copy, .phase8-changes.tgz)"
if [ -n "$(git status --porcelain)" ]; then
  git stash push -u -m "before plugin bundle $(date +%Y-%m-%d)" -- . ":!multicam-plugins.bundle" ":!apply-plugin-work.sh"
fi

echo "== 3/5 fast-forwarding main"
git fetch "$BUNDLE" main:plugin-work
git merge --ff-only plugin-work
git branch -d plugin-work
git log --oneline -10

if git stash list | head -1 | grep -q "before plugin bundle"; then
  echo "Stashed files that differ from the Phase 8 commit (nothing listed = identical,"
  echo "safe to 'git stash drop' later):"
  git diff --stat --diff-filter=M "stash@{0}" b6a8085 -- . || true
  git diff --stat --diff-filter=AM b6a8085 "stash@{0}^3" -- . ':!.phase8-changes.tgz' 2>/dev/null || true
fi

echo "== 4/5 installing (new packages: plugin-core, premiere-uxp, resolve-wi)"
pnpm install
uv sync
make fetch-models

echo "== 5/5 checks + plugin builds"
make check
pnpm --filter @multicam/plugin-core test
pnpm --filter @multicam/premiere-uxp test
pnpm --filter @multicam/premiere-uxp build
pnpm --filter @multicam/resolve-wi build
pnpm --filter @multicam/desktop test

cat <<'DONE'

All done. Next:
  * commit the updated pnpm-lock.yaml:  git add pnpm-lock.yaml && git commit -m "lockfile: plugin packages"
  * push:                               git push origin main
  * drop the stash if nothing was listed above:   git stash drop
  * Premiere: load apps/plugins/premiere-uxp/manifest.json in UXP Developer Tool,
    run the spike checklist in apps/plugins/premiere-uxp/README.md
  * Resolve:  cd apps/plugins/resolve-script && python3 -m multicam_resolve.install
  * Final Cut: export "Final Cut Pro (multicam clip)" in the app, File > Import > XML
DONE
