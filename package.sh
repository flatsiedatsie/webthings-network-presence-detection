#!/bin/bash

set -e

version=$(grep version package.json | cut -d: -f2 | cut -d\" -f2)

# Clean up from previous releases
rm -rf ._* *.tgz package
rm -f SHA256SUMS
#rm -rf ._*

# Put package together
mkdir package
cp -r pkg LICENSE *.json *.py package/
find package -type f -name '*.pyc' -delete
find package -type d -empty -delete
echo "prepared the files in the package directory"

# Generate checksums
cd package
find . -type f \! -name SHA256SUMS -exec sha256sum {} \; >> SHA256SUMS
cd ..
echo "generated checksums"

# Make the tarball
tar czf "network-presence-detection-adapter-${version}.tgz" package
sha256sum "network-presence-detection-adapter-${version}.tgz"
