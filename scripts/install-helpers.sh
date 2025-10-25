#!/bin/bash
# Shared installation helper functions
# Source this file from installation scripts: source "$(dirname "$0")/../../scripts/install-helpers.sh"

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
