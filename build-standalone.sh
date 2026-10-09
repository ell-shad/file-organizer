#!/bin/bash
# Build a fully self-contained executable with PySide6 bundled in.
# Output: dist/file-organizer (one file, no Python/Qt install needed to run).
#
#   ./build-standalone.sh
#
# Requires: pip install pyinstaller PySide6  (Linux glibc target).
# The binary is built for your distro's glibc; build on the oldest
# supported Debian/Ubuntu for the widest compatibility (CI does this on
# debian:stable-slim).
set -euo pipefail
cd "$(dirname "$0")"

OUTDIR="${1:-dist}"
VERSION=$(python3 -c "import re; print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('src/file_organizer/__init__.py').read()).group(1))")
PY="${PYTHON:-python3}"

mkdir -p "$OUTDIR"
BUILD_TMP=$(mktemp -d)
trap 'rm -rf "$BUILD_TMP"' EXIT

echo "Building self-contained file-organizer $VERSION …"

# Clean previous build metadata (keep .gitignore patterns in sync)
rm -rf build dist/file-organizer.spec

"$PY" -m PyInstaller \
  --onefile \
  --name file-organizer \
  --distpath "$BUILD_TMP" \
  --workpath "$BUILD_TMP/build" \
  --specpath "$BUILD_TMP" \
  --paths src \
  --noconfirm \
  --log-level WARN \
  packaging/pyinstaller_entry.py

mv "$BUILD_TMP/file-organizer" "$OUTDIR/file-organizer"
chmod 755 "$OUTDIR/file-organizer"

# Smoke test: the bundled binary must run its own CLI without any deps.
echo "Smoke-testing bundled binary …"
"$OUTDIR/file-organizer" --version
mkdir -p "$BUILD_TMP/sample" && echo x > "$BUILD_TMP/sample/a.jpg"
"$OUTDIR/file-organizer" scan "$BUILD_TMP/sample"

SIZE=$(du -h "$OUTDIR/file-organizer" | cut -f1)
echo "Created: $OUTDIR/file-organizer ($SIZE, fully self-contained)"
echo "Distribute this single file — no Python, PySide6, or apt needed to run."