#!/bin/bash
# Shared installation helper functions
# Source this file from installation scripts: source "$(dirname "$0")/../../scripts/install-helpers.sh"

# Add a user to a group (idempotent)
# Silently skips if group doesn't exist or user already in group
#
# Arguments:
#   $1 - User name to add to group
#   $2 - Group name
#   $3 - Optional description for logging (e.g., "for camera access")
#
# Behavior:
#   - Checks if group exists (silently returns if not)
#   - Checks if user is already in group
#   - Adds user to group if needed
#   - Prints status messages
#
# Example:
#   add_user_to_group "mcpserver" "video" "for camera access"
#   add_user_to_group "gardener-publisher" "mcpserver"
add_user_to_group() {
    local user="$1"
    local group="$2"
    local description="${3:-}"

    if [ -z "$user" ] || [ -z "$group" ]; then
        echo "ERROR: add_user_to_group requires user and group arguments" >&2
        return 1
    fi

    # Check if group exists
    if ! getent group "$group" > /dev/null 2>&1; then
        return 0  # Group doesn't exist, silently skip
    fi

    # Check if user is already in group
    if id -nG "$user" 2>/dev/null | grep -qw "$group"; then
        echo "✓ User $user already in $group group"
        return 0
    fi

    # Add user to group
    if [ -n "$description" ]; then
        echo "Adding $user to $group group ($description)..."
    else
        echo "Adding $user to $group group..."
    fi

    if ! usermod -a -G "$group" "$user"; then
        echo "✗ ERROR: Failed to add $user to $group group" >&2
        return 1
    fi

    echo "✓ User $user added to $group group"
}

# Install uv package manager for a specific user
# This ensures uv is installed and validates the installation
#
# Arguments:
#   $1 - Service user name (e.g., "mcpserver" or "gardener-publisher")
#
# Behavior:
#   - Checks if uv is already installed at ~/.local/bin/uv
#   - Installs uv if not present
#   - Validates installation succeeded
#   - Shows version information
#
# Example:
#   install_uv_for_user "mcpserver"
install_uv_for_user() {
    local service_user="$1"
    local user_home

    if [ -z "$service_user" ]; then
        echo "ERROR: install_uv_for_user requires service_user argument" >&2
        return 1
    fi

    # Get the user's home directory
    user_home=$(eval echo "~$service_user")
    local uv_bin="$user_home/.local/bin/uv"

    if [ -x "$uv_bin" ]; then
        local uv_version
        uv_version=$(sudo -u "$service_user" "$uv_bin" --version 2>/dev/null || echo "unknown")
        echo "✓ uv already installed for $service_user (version: $uv_version)"
    else
        echo "Installing uv package manager as $service_user..."
        echo ""

        # Run uv installation with visible output
        sudo -u "$service_user" bash -c "cd $user_home && curl -LsSf https://astral.sh/uv/install.sh | sh"
        local install_exit_code=$?

        echo ""

        # Validate installation
        if [ $install_exit_code -ne 0 ]; then
            echo "✗ ERROR: uv installation script failed with exit code $install_exit_code" >&2
            return 1
        fi

        if [ -x "$uv_bin" ]; then
            local uv_version
            uv_version=$(sudo -u "$service_user" "$uv_bin" --version 2>/dev/null || echo "unknown")
            echo "✓ uv installed successfully for $service_user (version: $uv_version)"
        else
            echo "✗ ERROR: uv installation failed - binary not found at $uv_bin" >&2
            return 1
        fi
    fi
}


# Setup ACL-based group access for a service account's home directory
# This allows group members to read files via SCP while maintaining security
#
# Arguments:
#   $1 - Service user name (e.g., "gardener" or "mcpserver")
#   $2 - Home directory path (e.g., "/home/gardener")
#
# Behavior:
#   - Installs acl package if not present (non-interactive)
#   - Sets read+execute ACLs on existing files
#   - Sets default ACLs so future files inherit group permissions
#
# Example:
#   setup_acl_group_access "gardener" "/home/gardener"
setup_acl_group_access() {
    local service_user="$1"
    local home_dir="$2"

    if [ -z "$service_user" ] || [ -z "$home_dir" ]; then
        echo "ERROR: setup_acl_group_access requires service_user and home_dir arguments" >&2
        return 1
    fi

    echo "Setting up ACLs for group access..."

    # Check if setfacl is available
    if ! command -v setfacl &> /dev/null; then
        echo "Installing acl package..."
        DEBIAN_FRONTEND=noninteractive apt-get update -qq
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends acl
    fi

    # Set ACLs for existing files (read + execute on directories only)
    setfacl -R -m "g:${service_user}:rX" "$home_dir"

    # Set default ACLs for future files (inherited by new files/directories)
    setfacl -R -d -m "g:${service_user}:rX" "$home_dir"

    echo "✓ ACLs configured for group access"
}

# Add the sudo invoking user to a service account's group
# This enables convenient read-only access via SCP
#
# Arguments:
#   $1 - Service user name / group name (e.g., "gardener")
#
# Behavior:
#   - Checks if SUDO_USER is set and not root
#   - Adds SUDO_USER to the service group if not already a member
#   - Notifies user they need to log out/in for group membership to take effect
#
# Example:
#   add_sudo_user_to_group "gardener"
add_sudo_user_to_group() {
    local service_group="$1"

    if [ -z "$service_group" ]; then
        echo "ERROR: add_sudo_user_to_group requires service_group argument" >&2
        return 1
    fi

    if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
        if id -nG "$SUDO_USER" | grep -qw "$service_group"; then
            echo "✓ User $SUDO_USER already in $service_group group"
        else
            echo "Adding $SUDO_USER to $service_group group..."
            usermod -a -G "$service_group" "$SUDO_USER"
            echo "✓ User $SUDO_USER added to $service_group group"
            echo "  Note: $SUDO_USER will need to log out and back in for group membership to take effect"
        fi
    fi
}
