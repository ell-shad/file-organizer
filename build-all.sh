#!/bin/bash
# Build every distributable artifact: .deb, source tarball, portable dir.
# Usage: ./build-all.sh [--output-dir dist]
set -euo pipefail
cd "$(dirname "$0")"
OUTDIR="${2:-dist}"
mkdir -p "$OUTDIR"
VERSION=$(python3 -c "import re; print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('src/file_organizer/__init__.py').read()).group(1))")

./build-deb.sh --output-dir "$OUTDIR"

# Source tarball (for releases / archives).
# Built from the working tree, not `git archive HEAD`: HEAD may lag behind
# uncommitted work, which once shipped the old v1 layout by mistake.
tar --exclude-vcs --exclude='__pycache__' -czf "$OUTDIR/file-organizer-$VERSION.tar.gz" \
  --transform "s,^,file-organizer-$VERSION/," \
  .github DEBIAN CONTRIBUTING.md LICENSE MANIFEST.in README.md CHANGELOG.md \
  build-deb.sh build-all.sh build-standalone.sh \
  man packaging pyproject.toml requirements.txt run.sh screenshots src tests usr \
  file-organizer.png
echo "Created: $OUTDIR/file-organizer-$VERSION.tar.gz"

# Portable directory: extract-and-run, no root needed
PORTABLE="$OUTDIR/file-organizer-$VERSION-portable"
rm -rf "$PORTABLE"
mkdir -p "$PORTABLE"
cp -r src usr man run.sh README.md CHANGELOG.md LICENSE "$PORTABLE/"
printf '#!/bin/bash\ncd "$(dirname "$0")"\nPYTHONPATH="$PWD/src" exec python3 -m file_organizer gui "$@"\n' \
  > "$PORTABLE/file-organizer-portable.sh"
chmod +x "$PORTABLE/file-organizer-portable.sh"
tar -czf "$PORTABLE.tar.gz" -C "$OUTDIR" "file-organizer-$VERSION-portable"
rm -rf "$PORTABLE"
echo "Created: $PORTABLE.tar.gz"

ls -la "$OUTDIR/"
