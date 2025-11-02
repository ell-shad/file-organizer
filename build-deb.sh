#!/bin/bash

# Create package structure
mkdir -p file-organizer/DEBIAN
mkdir -p file-organizer/usr/bin
mkdir -p file-organizer/usr/share/file-organizer
mkdir -p file-organizer/usr/share/applications
mkdir -p file-organizer/usr/share/pixmaps

# Copy files
cp DEBIAN/control file-organizer/DEBIAN/
cp DEBIAN/postinst file-organizer/DEBIAN/
chmod 755 file-organizer/DEBIAN/postinst

cp file_organizer.py file-organizer/usr/share/file-organizer/
cp usr/bin/file-organizer file-organizer/usr/bin/
chmod 755 file-organizer/usr/bin/file-organizer

cp usr/share/applications/file-organizer.desktop file-organizer/usr/share/applications/

if [ -f "file-organizer.png" ]; then
    cp file-organizer.png file-organizer/usr/share/pixmaps/
    echo "✓ Icon included in package"
else
    echo "✗ WARNING: file-organizer.png not found in current directory!"
    echo "  Create an icon or the app will use default icon"
fi

# Build package
dpkg-deb --build file-organizer

echo "Package created: file-organizer.deb"
echo "Install with: sudo dpkg -i file-organizer.deb"
