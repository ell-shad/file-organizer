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
         "$STAGE/usr/share/icons/hicolor/64x64/apps" \
         "$STAGE/usr/share/doc/file-organizer" "$STAGE/usr/share/man/man1"

sed "s/^Version:.*/Version: $VERSION/" DEBIAN/control > "$STAGE/DEBIAN/control"
cp DEBIAN/postinst "$STAGE/DEBIAN/postinst"
chmod 755 "$STAGE/DEBIAN/postinst"

cp -r src "$STAGE/usr/share/file-organizer/"
find "$STAGE/usr/share/file-organizer" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/usr/share/file-organizer" -type f -exec chmod 644 {} +
find "$STAGE/usr/share/doc" -type f -exec chmod 644 {} +
find "$STAGE" -type d -exec chmod 755 {} +

cp usr/bin/file-organizer "$STAGE/usr/bin/file-organizer"
chmod 755 "$STAGE/usr/bin/file-organizer"

cp usr/share/applications/file-organizer.desktop "$STAGE/usr/share/applications/"
chmod 644 "$STAGE/usr/share/applications/file-organizer.desktop"
# Debian policy: man pages and docs ship gzip-compressed.
if [ -f man/file-organizer.1 ]; then
    gzip -9 -n -c man/file-organizer.1 > "$STAGE/usr/share/man/man1/file-organizer.1.gz"
    chmod 644 "$STAGE/usr/share/man/man1/file-organizer.1.gz"
else
    echo "note: man page missing, skipping"
fi
cp README.md "$STAGE/usr/share/doc/file-organizer/" 2>/dev/null || true
cp LICENSE "$STAGE/usr/share/doc/file-organizer/copyright" 2>/dev/null || true
# changelog.gz: Debian-format entries, newest first.
{
    printf 'file-organizer (%s-1) unstable; urgency=medium\n' "$VERSION"
    printf '\n'
    printf '  * Release %s.\n' "$VERSION"
    printf '  * Modern Qt interface, safe move core, CLI, undo support.\n'
    printf '  * See README.md and the project CHANGELOG.md for details.\n'
    printf '\n'
    printf ' -- Elshad Guliyev <ellshad.012@gmail.com>  %s\n' "$(date -R)"
} | gzip -9 -n > "$STAGE/usr/share/doc/file-organizer/changelog.gz"
chmod 644 "$STAGE/usr/share/doc/file-organizer/changelog.gz"
find "$STAGE/usr/share/doc" -type f -exec chmod 644 {} +

if [ -f "file-organizer.png" ]; then
    cp file-organizer.png "$STAGE/usr/share/pixmaps/file-organizer.png"
    chmod 644 "$STAGE/usr/share/pixmaps/file-organizer.png"
    # The .desktop file uses the themed name "file-organizer", so the icon
    # must also live in an icon-theme directory. /usr/share/pixmaps alone is
    # not on the theme search path and yields a blank icon in the app menu.
    ICON_SIZE=$(python3 -c "
from struct import unpack
with open('file-organizer.png','rb') as f:
    f.read(16)
    w, h = unpack('>II', f.read(8))
print(f'{w}x{h}')
" 2>/dev/null || echo "64x64")
    mkdir -p "$STAGE/usr/share/icons/hicolor/$ICON_SIZE/apps"
    cp file-organizer.png "$STAGE/usr/share/icons/hicolor/$ICON_SIZE/apps/file-organizer.png"
    find "$STAGE/usr/share/icons" -type f -exec chmod 644 {} +
    find "$STAGE/usr/share/icons" -type d -exec chmod 755 {} +
    echo "✓ icon included (hicolor/$ICON_SIZE/apps + pixmaps)"
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
