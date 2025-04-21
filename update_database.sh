#!/usr/bin/env bash

set -o noclobber
set -euo pipefail
trap 'echo error at about $LINENO' ERR
IFS=$'\n\t'

# Destination path
DEST="all.json"
OUTPUT_DATABASE="data/hot_100.sqlite"
# Download URL
URL="https://raw.githubusercontent.com/mhollingshead/billboard-hot-100/main/all.json"

## Use curl to download the file
#if curl -L "$URL" -o "$DEST"; then
#  echo "Downloaded to $DEST"
#else
#  echo "Download failed"
#fi

./src/create_database.py \
  --input "${DEST}" \
  --output "${OUTPUT_DATABASE}"