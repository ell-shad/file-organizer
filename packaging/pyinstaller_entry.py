# Entry point for PyInstaller (a package __main__.py cannot be used as the
# script directly because of its relative import). Do not run this by hand.
from file_organizer.cli import main

if __name__ == "__main__":
    raise SystemExit(main())