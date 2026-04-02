#!/bin/bash

# Set the root of the project (edit this if needed)
AF3_DIR="."

# List of required subfolders
folders=(
  "AF3_output"
  "ChimeraX"
  "ChimeraX/cx_scripts"
  "config"
  "input"
  "Merge"
  "Mergemerge"
  "Metrics_plots"
  "sequences"
  "src/logs"
)

echo "Creating missing folders in $AF3_DIR..."

for folder in "${folders[@]}"; do
  full_path="$AF3_DIR/$folder"
  if [ ! -d "$full_path" ]; then
    mkdir -p "$full_path"
    echo "Created: $full_path"
  else
    echo "Already exists: $full_path"
  fi
done

echo "✅ Folder setup complete."
