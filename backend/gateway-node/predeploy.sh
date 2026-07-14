#!/usr/bin/env bash
# Run this before `fly deploy` (from this directory).
#
# Fly's Docker build context is whatever directory you run `fly deploy` from
# — here, backend/gateway-node/ — so it can't COPY the sibling ../../widget/
# folder. This vendors a copy into ./widget/ first so the Dockerfile can bundle
# it and GET /widget.js keeps working once deployed. (The Chrome extension
# loads its own bundled copy at extension/translation-widget.js, so this only
# matters for the console-snippet loading path.)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HERE/widget"
cp "$HERE/../../widget/translation-widget.js" "$HERE/widget/translation-widget.js"
echo "Vendored widget/translation-widget.js into backend/gateway-node/widget/ for deploy."
