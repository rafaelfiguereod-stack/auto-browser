#!/usr/bin/env bash
set -e

echo "=== Auto Browser Docker Start ==="

# Start Docker daemon if not running
if ! docker info > /dev/null 2>&1; then
    echo "Starting Docker daemon..."
    sudo service docker start
    sleep 3
fi

echo "Docker daemon: OK"
docker --version

# Navigate to this script's directory (auto-browser root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Working in: $SCRIPT_DIR"
cd "$SCRIPT_DIR"

echo ""
echo "Starting auto-browser stack..."
echo "  Controller API: http://localhost:8000"
echo "  noVNC browser:  http://localhost:6080"
echo ""

docker compose up --build
