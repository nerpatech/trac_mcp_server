#!/bin/bash
# Install trac-mcp-server binary to ~/.local/bin

set -e

BINARY="dist/trac-mcp-server"
DEST="${HOME}/.local/bin/trac-mcp-server"

# Check binary exists
if [ ! -f "$BINARY" ]; then
    echo "ERROR: Binary not found at $BINARY"
    echo "Run ./build.sh first."
    exit 1
fi

# Create destination directory if needed
mkdir -p "${HOME}/.local/bin"

# Copy binary
echo "Installing trac-mcp-server to $DEST..."
cp "$BINARY" "$DEST"
chmod +x "$DEST"

# Verify
echo "Verifying installation..."
"$DEST" --version

echo ""
echo "Installation complete: $DEST"
echo ""
echo "Make sure ~/.local/bin is in your PATH:"
echo '  export PATH="$HOME/.local/bin:$PATH"'
