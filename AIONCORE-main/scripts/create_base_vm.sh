#!/bin/bash
set -euo pipefail

# Base VM image creation script for AION Core
# Downloads Ubuntu 22.04 cloud image and prepares a qcow2 base disk.

IMAGE_DIR="/var/lib/libvirt/images"
BASE_IMAGE="$IMAGE_DIR/base.qcow2"
CLOUD_IMG_URL="https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
TEMP_IMG="/tmp/ubuntu-22.04-server-cloudimg-amd64.img"

if [ -f "$BASE_IMAGE" ]; then
    echo "Base image already exists at $BASE_IMAGE, skipping."
    exit 0
fi

echo "Creating base VM image..."

# Ensure directory exists
sudo mkdir -p "$IMAGE_DIR"

# Download Ubuntu cloud image
echo "Downloading Ubuntu 22.04 cloud image..."
wget -O "$TEMP_IMG" "$CLOUD_IMG_URL"

# Convert and place as base image
echo "Converting to qcow2 format..."
sudo qemu-img convert -f qcow2 -O qcow2 "$TEMP_IMG" "$BASE_IMAGE"

# Resize to 10GB (can be expanded per-clone later)
echo "Resizing base image to 10GB..."
sudo qemu-img resize "$BASE_IMAGE" 10G

# Cleanup
rm -f "$TEMP_IMG"

echo ""
echo "Base image created successfully at: $BASE_IMAGE"
echo "Disk info:"
sudo qemu-img info "$BASE_IMAGE"
