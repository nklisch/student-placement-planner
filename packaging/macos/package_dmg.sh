#!/bin/sh
set -eu

APP_PATH=${1:?Usage: package_dmg.sh path/to/App.app version}
VERSION=${2:?Usage: package_dmg.sh path/to/App.app version}
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
RELEASE_DIR="$ROOT/release"
DMG="$RELEASE_DIR/Student-Placement-Planner-${VERSION}-macOS-Apple-Silicon.dmg"
STAGING=$(mktemp -d)
trap 'rm -rf "$STAGING"' EXIT
mkdir -p "$RELEASE_DIR"

if [ -n "${MACOS_SIGN_IDENTITY:-}" ]; then
  python3 "$ROOT/packaging/macos/sign_app.py" "$APP_PATH" "$MACOS_SIGN_IDENTITY"
else
  # Ad-hoc signing preserves bundle integrity for preview builds but is not
  # Apple-trusted. The release notes explain the one-time right-click/Open step.
  python3 "$ROOT/packaging/macos/sign_app.py" "$APP_PATH" -
fi

cp -R "$APP_PATH" "$STAGING/Student Placement Planner.app"
ln -s /Applications "$STAGING/Applications"
attempt=1
while :; do
  rm -f "$DMG"
  if hdiutil create \
    -volname "Student Placement Planner" \
    -srcfolder "$STAGING" \
    -format UDZO \
    -ov \
    "$DMG" >/dev/null; then
    break
  fi
  if [ "$attempt" -ge 3 ]; then
    echo "Could not create the disk image after $attempt attempts" >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sync
  sleep 3
done

if [ -n "${MACOS_SIGN_IDENTITY:-}" ]; then
  codesign --force --options runtime --timestamp --sign "$MACOS_SIGN_IDENTITY" "$DMG"
fi
printf '%s\n' "$DMG"
