#!/bin/bash

# AnOS Welcome Build Script
# Maintainer: minhmc2007 <quangminh21072010@gmail.com>

set -e # Exit on error

# The package name for Arch (hyphenated)
PKG_NAME="anos-welcome"
# The actual binary name produced by Flutter (underscored)
BINARY_NAME="anos_welcome"
VERSION="1.0.1"

BUILD_DIR="$(pwd)/dist/pkg"
RELEASE_DIR="$(pwd)/build/linux/x64/release/bundle"

echo "--- [AnOS Build] Initializing build process for $PKG_NAME ---"

# 1. Clean previous builds
rm -rf "$BUILD_DIR"
rm -f "$PKG_NAME-$VERSION-1-x86_64.pkg.tar.zst"

# 2. Build the Flutter application
echo "--- [AnOS Build] Compiling Flutter binary ---"
flutter clean
flutter pub get
flutter build linux --release

# 3. Create build directory structure
mkdir -p "$BUILD_DIR"

# 4. Generate the PKGBUILD
echo "--- [AnOS Build] Generating PKGBUILD ---"

cat <<EOF > "$BUILD_DIR/PKGBUILD"
# Maintainer: minhmc2007 <quangminh21072010@gmail.com>
pkgname=$PKG_NAME
pkgver=$VERSION
pkgrel=1
pkgdesc="Welcome app for AnOS Linux (Material You)"
arch=('x86_64')
license=('MIT')
depends=('gtk3' 'glib2' 'libx11' 'libxkbcommon' 'libxcursor' 'libxrandr' 'libxi' 'libappindicator-gtk3')

package() {
    # Install binary (rename from underscore to hyphenated pkgname)
    install -Dm755 "$RELEASE_DIR/$BINARY_NAME" "\$pkgdir/usr/bin/$PKG_NAME"

    # Install Flutter data and libraries
    mkdir -p "\$pkgdir/usr/lib/$PKG_NAME"
    cp -r "$RELEASE_DIR/data" "\$pkgdir/usr/lib/$PKG_NAME/"
    cp -r "$RELEASE_DIR/lib" "\$pkgdir/usr/lib/$PKG_NAME/"

    # Create a wrapper script to handle the library path
    # Flutter apps expect the 'lib' folder to be relative to the binary
    # We use a symlink or a small shell wrapper
    mkdir -p "\$pkgdir/usr/bin"
    echo -e "#!/bin/sh\nexec /usr/lib/$PKG_NAME/$BINARY_NAME \"\\\$@\"" > "\$pkgdir/usr/bin/$PKG_NAME"
    chmod +x "\$pkgdir/usr/bin/$PKG_NAME"

    # Move the actual binary to the internal lib folder
    install -Dm755 "$RELEASE_DIR/$BINARY_NAME" "\$pkgdir/usr/lib/$PKG_NAME/$BINARY_NAME"

    # Install desktop entry
    install -Dm644 /dev/stdin "\$pkgdir/usr/share/applications/$PKG_NAME.desktop" <<DESKTOP
[Desktop Entry]
Name=AnOS Welcome
Comment=Welcome to AnOS Linux
Exec=$PKG_NAME
Icon=preferences-desktop-color
Terminal=false
Type=Application
Categories=System;
StartupNotify=true
DESKTOP
}
EOF

# 5. Build and install the package
echo "--- [AnOS Build] Creating Arch package ---"
cd "$BUILD_DIR"
makepkg -srcf --noconfirm

