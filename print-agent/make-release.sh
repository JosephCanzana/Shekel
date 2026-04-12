#!/bin/bash
# make-release.sh — run from the print-agent directory
# Usage: bash make-release.sh
# Output: releases/shekel-agent-linux.zip

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASE_DIR="$SCRIPT_DIR/releases"

echo "========================================"
echo "  Shekel Print Agent - Build & Package"
echo "========================================"
echo ""

# ── Check we're in the right directory ──────────────────────────
if [ ! -f "$SCRIPT_DIR/agent.py" ]; then
    echo "ERROR: Run this from the print-agent directory."
    exit 1
fi

# ── Activate venv if present ────────────────────────────────────
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo "[1/4] Activating virtual environment..."
    source "$SCRIPT_DIR/venv/bin/activate"
else
    echo "[1/4] No venv found, using system Python..."
fi

# ── Build Linux binary ──────────────────────────────────────────
echo "[2/4] Building Linux binary..."
python build.py

BINARY="$SCRIPT_DIR/dist/shekel-agent"
if [ ! -f "$BINARY" ]; then
    echo "ERROR: Build failed. Binary not found at $BINARY"
    exit 1
fi
echo "  Binary: $BINARY ($(du -sh "$BINARY" | cut -f1))"

# ── Create releases directory ───────────────────────────────────
echo "[3/4] Creating release package..."
mkdir -p "$RELEASE_DIR"

# Linux package
ZIP_LINUX="$RELEASE_DIR/shekel-agent-linux.zip"
zip -j "$ZIP_LINUX" \
    "$BINARY" \
    "$SCRIPT_DIR/setup/setup-linux.sh"
echo "  Created: $ZIP_LINUX"

# Windows package (only if .exe exists)
EXE="$SCRIPT_DIR/dist/shekel-agent.exe"
if [ -f "$EXE" ]; then
    ZIP_WINDOWS="$RELEASE_DIR/shekel-agent-windows.zip"
    zip -j "$ZIP_WINDOWS" \
        "$EXE" \
        "$SCRIPT_DIR/setup/setup-windows.bat" \
        "$SCRIPT_DIR/setup/uninstall-windows.bat"
    echo "  Created: $ZIP_WINDOWS"
else
    echo "  Skipping Windows package (no .exe found)"
    echo "  Build on Windows first to include it"
fi

# macOS package (only if macos binary exists)
MACOS_BIN="$SCRIPT_DIR/dist/shekel-agent-macos"
if [ -f "$MACOS_BIN" ]; then
    ZIP_MACOS="$RELEASE_DIR/shekel-agent-macos.zip"
    zip -j "$ZIP_MACOS" \
        "$MACOS_BIN" \
        "$SCRIPT_DIR/setup/setup-macos.sh"
    echo "  Created: $ZIP_MACOS"
else
    echo "  Skipping macOS package (no macos binary found)"
    echo "  Build on macOS first to include it"
fi

# ── Summary ─────────────────────────────────────────────────────
echo ""
echo "[4/4] Done. Release packages:"
ls -lh "$RELEASE_DIR"/*.zip 2>/dev/null || echo "  No packages found"

echo ""
echo "========================================"
echo "  Packages saved to: releases/"
echo ""
echo "  Distribute to users:"
echo "  Linux   → shekel-agent-linux.zip"
echo "  Windows → shekel-agent-windows.zip (build on Windows first)"
echo "  macOS   → shekel-agent-macos.zip   (build on macOS first)"
echo "========================================"