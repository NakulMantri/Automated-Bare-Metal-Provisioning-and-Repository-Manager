#!/usr/bin/env bash

# Setup GPG key pair for automated RPM signing

set -euo pipefail

KEY_NAME="custom-internal"
KEY_EMAIL="admin@infra.local"
OUTPUT_DIR="repo"

echo "Initializing GPG signing automation..."

# Ensure gpg is available
if ! command -v gpg &> /dev/null; then
    echo "ERROR: gpg command not found. Please install gnupg."
    exit 1
fi

# Check if key already exists
if gpg --list-keys "$KEY_NAME" &> /dev/null; then
    echo "GPG key '$KEY_NAME' already exists in the keyring. Skipping generation."
else
    echo "Generating new GPG key pair for '$KEY_NAME'..."
    
    # Write temporary batch configuration file
    BATCH_CONFIG=$(mktemp)
    cat <<EOF > "$BATCH_CONFIG"
Key-Type: RSA
Key-Length: 2048
Subkey-Type: RSA
Subkey-Length: 2048
Name-Real: Custom Provisioning Admin
Name-Email: $KEY_EMAIL
Expire-Date: 0
%no-ask-passphrase
%no-protection
%commit
EOF

    # Generate key in batch mode
    gpg --batch --generate-key "$BATCH_CONFIG"
    rm -f "$BATCH_CONFIG"
    echo "GPG key pair generated successfully."
fi

# Export public GPG key to repo directory
mkdir -p "$OUTPUT_DIR"
PUBKEY_PATH="$OUTPUT_DIR/RPM-GPG-KEY-$KEY_NAME"
echo "Exporting public key to '$PUBKEY_PATH'..."
gpg --armor --export --output "$PUBKEY_PATH" "$KEY_NAME"

echo "✔ GPG signing key setup completed successfully!"
