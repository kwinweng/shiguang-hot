#!/bin/sh
# Persist only the collected database; a rejected push must stop publication.
set -eu

if git diff HEAD --quiet -- tg.db; then
    printf '%s\n' 'No database changes to persist.'
    exit 0
fi
if [ "$(git branch --show-current)" != main ]; then
    echo 'Database persistence requires main.' >&2
    exit 1
fi
check_clean() {
    if [ -n "$(git status --porcelain --untracked-files=normal -- . ':!tg.db')" ]; then
        echo 'Refusing reset: changes outside tg.db; preserve and resolve them first.' >&2
        exit 1
    fi
}
check_clean
base=$(git rev-parse HEAD)
backup=$(mktemp -d "$(git rev-parse --absolute-git-dir)/persist-db.XXXXXX")
cp -- tg.db "$backup/tg.db"
# Keep the snapshot on every failure, including fetch, commit hook and push errors.
trap 'echo "Local database backup kept at $backup/tg.db" >&2' EXIT
prepare_commit() {
    git fetch origin main
    if ! git merge-base --is-ancestor "$base" origin/main; then
        echo 'Local history diverged; run box initial sync before persistence.' >&2
        exit 1
    fi
    if [ -n "$(git log --format=%H "$base..origin/main" -- tg.db)" ]; then
        echo 'Remote changed tg.db since scrape base; refusing overwrite. Operations must resolve database writers.' >&2
        exit 1
    fi
    check_clean
    git reset --hard origin/main
    cp -- "$backup/tg.db" tg.db
    git add -- tg.db
    git -c user.name=bot -c user.email=bot@users.noreply.github.com \
        commit --only -m "data $(date -u +%FT%H)" -- tg.db
}
prepare_commit
if ! ALLOW_MAIN_PUSH=publish git push origin HEAD:refs/heads/main; then
    attempt=$(git rev-parse HEAD)
    git fetch origin main
    if git merge-base --is-ancestor origin/main "$attempt"; then
        echo 'Push failed without a remote advance; refusing retry.' >&2
        exit 1
    fi
    prepare_commit
    ALLOW_MAIN_PUSH=publish git push origin HEAD:refs/heads/main
fi
trap - EXIT
rm -rf -- "$backup"
