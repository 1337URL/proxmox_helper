#! /bin/bash

set -e

mkdir -p python3-proxmox-helper/DEBIAN
mkdir -p python3-proxmox-helper/usr/lib/python3/dist-packages/
cp -r ./proxmox_helper python3-proxmox-helper/usr/lib/python3/dist-packages/
rm -rf python3-proxmox-helper/usr/lib/python3/dist-packages/proxmox_helper/__pycache__

cat << 'EOF' > python3-proxmox-helper/DEBIAN/control 
Package: python3-proxmox-helper
Version: 1.0.0
Architecture: all
Depends: python3-proxmoxer (>=2.0.1-1), python3:any
Maintainer: Urho Laurinen <url.sequel@gmail.com>
Description: Some helpful proxmox functions 
EOF

echo 2.0 > python3-proxmox-helper/DEBIAN/debian-binary

dpkg-deb --build python3-proxmox-helper

rm -rf python3-proxmox-helper