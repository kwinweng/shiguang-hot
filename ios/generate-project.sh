#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
asset=App/Assets.xcassets/AppIcon.appiconset
# iOS masks the square icon itself. Start from the approved opaque master,
# not from the smaller, already-resampled PWA icons.
sips -z 1024 1024 ../web-v11/brand/kangaroo-source.png --out "$asset/AppIcon.png" >/dev/null
xcodegen generate --spec project.yml
