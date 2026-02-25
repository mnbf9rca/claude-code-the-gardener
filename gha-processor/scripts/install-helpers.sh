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
    # Use getent and parse the comma-separated member list
    # Format: groupname:x:gid:member1,member2,member3
    local members
    members=$(getent group "$group" | cut -d: -f4)

    # Check if user appears in the comma-separated list (exact match)
    if [[ ",$members," == *",$user,"* ]]; then
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

# Initialize a git repository for backup purposes
# Creates repo, sets user/email, creates .gitignore, makes initial commit
#
# Arguments:
#   $1 - Service user name (e.g., "mcpserver" or "gardener")
#   $2 - Repository directory path (absolute path)
#   $3 - Repository name for display (e.g., "MCP Data Backup")
#   $4 - Git user name (e.g., "MCP Server Backup")
#   $5 - Git user email (e.g., "backup@mcpserver.local")
#   $6 - Optional .gitignore content (pass empty string to skip)
#
# Behavior:
#   - Skips if .git directory already exists
#   - Initializes with main branch
#   - Configures user name and email
#   - Creates .gitignore if content provided
#   - Makes initial commit (if files exist)
#
# Example:
#   init_git_backup_repo "mcpserver" "/home/mcpserver/data" "MCP data" \
#       "MCP Server Backup" "backup@mcpserver.local" "*.jpg\n*.png"
init_git_backup_repo() {
    local service_user="$1"
    local repo_dir="$2"
    local display_name="$3"
    local git_user_name="$4"
    local git_user_email="$5"
    local gitignore_content="${6:-}"

    if [ -z "$service_user" ] || [ -z "$repo_dir" ] || [ -z "$display_name" ] || \
       [ -z "$git_user_name" ] || [ -z "$git_user_email" ]; then
        echo "ERROR: init_git_backup_repo requires all arguments" >&2
        return 1
    fi

    # Check if already initialized
    if [ -d "$repo_dir/.git" ]; then
        echo "✓ Git repository already exists"
        return 0
    fi

    echo "  Initializing git repository in $repo_dir"

    # Initialize with main branch
    sudo -u "$service_user" bash -c "cd '$repo_dir' && git init --initial-branch=main"

    # Configure user
    sudo -u "$service_user" bash -c "cd '$repo_dir' && git config user.name '$git_user_name'"
    sudo -u "$service_user" bash -c "cd '$repo_dir' && git config user.email '$git_user_email'"

    # Create .gitignore if content provided
    if [ -n "$gitignore_content" ]; then
        sudo -u "$service_user" bash -c "cat > '$repo_dir/.gitignore' << 'EOF'
$gitignore_content
EOF"
    fi

    # Make initial commit
    sudo -u "$service_user" bash -c "cd '$repo_dir' && git add -A && git commit -m 'Initial commit' || true"

    echo "✓ Git repository initialized"
}

# Add a directory to system-level git safe.directory config
# Prevents "dubious ownership" errors for group members
#
# Arguments:
#   $1 - Directory path to add (absolute path)
#
# Behavior:
#   - Checks if directory is already in system gitconfig
#   - Adds if not present (idempotent)
#   - Requires root privileges (should be called from install scripts running as sudo)
#
# Example:
#   add_safe_directory "/home/mcpserver/data"
add_safe_directory() {
    local dir_path="$1"

    if [ -z "$dir_path" ]; then
        echo "ERROR: add_safe_directory requires directory path argument" >&2
        return 1
    fi

    # Check if already in system gitconfig
    if git config --system --get-all safe.directory | grep -qx "$dir_path" 2>/dev/null; then
        return 0  # Already present, silently skip
    fi

    # Add to system gitconfig
    git config --system --add safe.directory "$dir_path"
}
