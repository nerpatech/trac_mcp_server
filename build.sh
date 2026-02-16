#!/bin/bash
# Build standalone binary for trac-mcp-server using PyInstaller

set -e

echo "==================================================================="
echo "  Building standalone binary: trac-mcp-server"
echo "==================================================================="
echo ""

# --- Pre-flight checks --------------------------------------------------------

if ! python -c "import PyInstaller" 2>/dev/null; then
    echo "PyInstaller not found. Installing dev dependencies..."
    pip install -e ".[dev]"
fi

# --- Clean previous builds ----------------------------------------------------

echo "Cleaning previous build artifacts..."
rm -rf build/ dist/ *.spec

# --- Hidden imports -----------------------------------------------------------

HIDDEN_IMPORTS=(
    # Root package
    trac_mcp_server
    trac_mcp_server.config
    trac_mcp_server.config_loader
    trac_mcp_server.config_schema
    trac_mcp_server.file_handler
    trac_mcp_server.logger
    trac_mcp_server.validators
    trac_mcp_server.version

    # core/ subpackage
    trac_mcp_server.core
    trac_mcp_server.core.client
    trac_mcp_server.core.async_utils

    # converters/ subpackage
    trac_mcp_server.converters
    trac_mcp_server.converters.common
    trac_mcp_server.converters.tracwiki_to_markdown
    trac_mcp_server.converters.markdown_to_tracwiki

    # detection/ subpackage
    trac_mcp_server.detection
    trac_mcp_server.detection.capabilities
    trac_mcp_server.detection.processor_utils
    trac_mcp_server.detection.web_scraper

    # mcp/ subpackage
    trac_mcp_server.mcp
    trac_mcp_server.mcp.server
    trac_mcp_server.mcp.lifespan
    trac_mcp_server.mcp.tools
    trac_mcp_server.mcp.tools.errors
    trac_mcp_server.mcp.tools.ticket_read
    trac_mcp_server.mcp.tools.ticket_write
    trac_mcp_server.mcp.tools.wiki_read
    trac_mcp_server.mcp.tools.wiki_write
    trac_mcp_server.mcp.tools.wiki_file
    trac_mcp_server.mcp.tools.milestone
    trac_mcp_server.mcp.tools.sync
    trac_mcp_server.mcp.tools.system
    trac_mcp_server.mcp.resources
    trac_mcp_server.mcp.resources.wiki

    # sync/ subpackage
    trac_mcp_server.sync
    trac_mcp_server.sync.engine
    trac_mcp_server.sync.mapper
    trac_mcp_server.sync.merger
    trac_mcp_server.sync.models
    trac_mcp_server.sync.reporter
    trac_mcp_server.sync.resolver
    trac_mcp_server.sync.state

    # Third-party libraries
    xmlrpc.client
    mistune
    lxml
    cssselect
    urllib3
    charset_normalizer
    mcp
    mcp.server
    mcp.server.stdio
    mcp.server.models
    mcp.types
    pydantic
    pydantic_core
    yaml
    anyio
    dotenv
    merge3
)

# Build hidden-import flags
IMPORT_FLAGS=""
for mod in "${HIDDEN_IMPORTS[@]}"; do
    IMPORT_FLAGS="$IMPORT_FLAGS --hidden-import $mod"
done

# --- Build --------------------------------------------------------------------

echo "Running PyInstaller..."
pyinstaller \
    --onefile \
    --console \
    --name trac-mcp-server \
    --paths src \
    $IMPORT_FLAGS \
    --exclude-module logfire \
    --clean \
    src/trac_mcp_server/mcp/__main__.py

# --- Verify -------------------------------------------------------------------

if [ -f "dist/trac-mcp-server" ]; then
    echo ""
    echo "==================================================================="
    echo "  Build successful!"
    echo "==================================================================="
    echo ""
    echo "Binary location: $(pwd)/dist/trac-mcp-server"
    echo "Binary size: $(du -h dist/trac-mcp-server | cut -f1)"
    echo ""

    # Smoke test
    echo "Smoke test..."
    ./dist/trac-mcp-server --version
    echo ""

    echo "Build complete! You can run the binary with:"
    echo "  ./dist/trac-mcp-server --help"
    echo ""
elif [ -f "dist/trac-mcp-server.exe" ]; then
    echo ""
    echo "==================================================================="
    echo "  Build successful!"
    echo "==================================================================="
    echo ""
    echo "Binary location: $(pwd)/dist/trac-mcp-server.exe"
    echo "Binary size: $(du -h dist/trac-mcp-server.exe | cut -f1)"
    echo ""

    # Smoke test
    echo "Smoke test..."
    ./dist/trac-mcp-server.exe --version
    echo ""

    echo "Build complete! You can run the binary with:"
    echo "  ./dist/trac-mcp-server.exe --help"
    echo ""
else
    echo ""
    echo "ERROR: Binary not found after build!"
    exit 1
fi
