#!/bin/bash
# LCSC-AD-Transfer Converter Service Launcher (Linux / macOS)

echo "================================================"
echo "  LCSC-AD-Transfer Converter Service"
echo "================================================"
echo ""

cd "$(dirname "$0")/converter"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js not found. Install Node.js 16+"
    echo "  https://nodejs.org/"
    exit 1
fi

# Install dependencies (first run)
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
    echo ""
fi

echo "Starting server on http://localhost:3001"
echo ""
node server.js

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] Server failed to start."
    echo "Possible causes:"
    echo "  1. Port 3001 in use: lsof -i :3001"
    echo "  2. Missing dependencies: cd converter && npm install"
    echo "  3. jsapi.min.js missing from converter/ folder"
fi
