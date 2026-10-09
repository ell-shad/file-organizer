#!/bin/bash
# Run File Organizer straight from source — no installation, no root.
#
#   ./run.sh scan ~/Downloads                  # CLI, standard library only
#   ./run.sh organize ~/Downloads --dry-run
#   ./run.sh                                   # GUI (Qt if present, else legacy Tk)
#
# GUI requirements (one of):
#   sudo apt install python3-pyside6           # modern Qt interface
#   sudo apt install python3-tk                # legacy Tk fallback (+ --toolkit tk)
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
if [ $# -eq 0 ]; then
    set -- gui
fi
exec python3 -m file_organizer "$@"
