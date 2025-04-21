#!/usr/bin/env bash

set -o noclobber
set -euo pipefail
trap 'echo error at about $LINENO' ERR
IFS=$'\n\t'

# Destination path
DEST="all.json"

# Download URL
URL="https://raw.githubusercontent.com/mhollingshead/billboard-hot-100/main/all.json"

# Use curl to download the file
if curl -L "$URL" -o "$DEST"; then
  echo "Downloaded to $DEST"
else
  echo "Download failed"
fi

./create_database.py \
  --input "${DEST}"