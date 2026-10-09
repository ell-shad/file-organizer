#!/bin/bash
# Build the .deb package (Debian/Ubuntu/Mint/Pop!_OS/…).
# Usage: ./build-deb.sh [--output-dir DIR]
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(python3 -c "import re; print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('src/file_organizer/__init__.py').read()).group(1))")
PKG_NAME="file-organizer_${VERSION}_all"
WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
OUTDIR="${2:-.}"
mkdir -p "$OUTDIR"
STAGE="$WORKDIR/$PKG_NAME"

echo "Building $PKG_NAME …"

mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/usr/share/file-organizer" \
         "$STAGE/usr/share/applications" "$STAGE/usr/share/pixmaps" \
         "$STAGE/usr/share/doc/file-organizer" "$STAGE/usr/share/man/man1"

sed "s/^Version:.*/Version: $VERSION/" DEBIAN/control > "$STAGE/DEBIAN/control"
cp DEBIAN/postinst "$STAGE/DEBIAN/postinst"
chmod 755 "$STAGE/DEBIAN/postinst"

cp -r src "$STAGE/usr/share/file-organizer/"
find "$STAGE/usr/share/file-organizer" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/usr/share/file-organizer" "$STAGE/usr/share/doc" -type f -exec chmod 644 {} +

cp usr/bin/file-organizer "$STAGE/usr/bin/file-organizer"
chmod 755 "$STAGE/usr/bin/file-organizer"

cp usr/share/applications/file-organizer.desktop "$STAGE/usr/share/applications/"
cp man/file-organizer.1 "$STAGE/usr/share/man/man1/" 2>/dev/null || echo "note: man page missing, skipping"
cp README.md CHANGELOG.md LICENSE "$STAGE/usr/share/doc/file-organizer/" 2>/dev/null || true

if [ -f "file-organizer.png" ]; then
    cp file-organizer.png "$STAGE/usr/share/pixmaps/file-organizer.png"
    echo "✓ icon included"
else
    echo "✗ WARNING: file-organizer.png not found — app will use a fallback icon"
fi

dpkg-deb --root-owner-group --build "$STAGE" "$OUTDIR/${PKG_NAME}.deb"
echo "Created: $OUTDIR/${PKG_NAME}.deb"
echo "Install with: sudo apt install ./$OUTDIR/${PKG_NAME}.deb"
if command -v lintian >/dev/null 2>&1; then
    echo "--- lintian ---"
    lintian "$OUTDIR/${PKG_NAME}.deb" || true
fi
