#!/bin/bash
# Process all client folders - rename transcripts and update context
# Usage: ./process-all-clients.sh

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$( cd "$SCRIPT_DIR/../.." && pwd )"

cd "$ROOT_DIR"

echo "Processing all client folders..."
echo ""

# Process any directory that has context.md (client folder), skip _*, Archive, Templates
for client in */; do
    client="${client%/}"
    if [ ! -d "$client" ] || [ ! -f "$client/context.md" ]; then
        continue
    fi
    case "$client" in
        _*|Archive|Templates) continue ;;
    esac
    echo "=== Processing $client ==="
    
    # Rename transcripts
    python3 "$SCRIPT_DIR/rename-existing-transcripts.py" "$client" 2>&1 | tail -3
    
    # Update context
    python3 "$SCRIPT_DIR/update-context.py" "$client" 2>&1 | grep -E "(Updating|Found|Updated|Done)" || echo "✓ Updated $client"
    
    echo ""
done

echo "Done processing all clients!"

# Rebuild workspace-wide transcript index
python3 "$SCRIPT_DIR/build-transcript-index.py"
