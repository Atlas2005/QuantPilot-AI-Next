#!/usr/bin/env sh
set -eu

name="${1:-}"

if [ -z "$name" ]; then
    echo "Prototype environment name is required." >&2
    exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
env_root="$repo_root/.venv-prototypes"
env_path="$env_root/$name"

mkdir -p "$env_root"

if [ -d "$env_path" ]; then
    echo "Prototype environment already exists: $env_path"
else
    python -m venv "$env_path"
    echo "Created prototype environment: $env_path"
fi

echo ""
echo "Activate with:"
echo ". .venv-prototypes/$name/bin/activate"
echo ""
echo "Package installation must be separately approved."
echo "This helper does not install packages, modify pyproject.toml, or run prototypes."
