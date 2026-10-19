#!/bin/sh
# Persist only the collected database; a rejected push must stop publication.
set -eu

git add -- tg.db
if git diff --cached --quiet -- tg.db; then
    printf '%s\n' 'No database changes to persist.'
    exit 0
fi
git -c user.name=bot -c user.email=bot@users.noreply.github.com \
    commit --only -m "data $(date -u +%FT%H)" -- tg.db
git push origin HEAD:refs/heads/main
