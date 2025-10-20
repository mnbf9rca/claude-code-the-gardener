#!/usr/bin/env python3
"""
Standalone SMTP configuration checker

Tests email notification functionality by sending a test message.
Reads SMTP configuration from .env file.

Usage:
    From the app directory:
        uv run python scripts/check_smtp.py
"""

import sys
import os
from pathlib import Path

# Add parent (app) directory to path so we can import tools
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from tools.human_messages import _send_email_notification


def main():
    """Send a test email notification"""
    # Load environment variables
    load_dotenv()

    # Check if SMTP is configured
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_to = os.getenv("SMTP_TO")
    smtp_from = os.getenv("SMTP_FROM")

    # TLS configuration
    smtp_port_int = int(smtp_port)
    smtp_use_tls_default = "true" if smtp_port_int == 587 else "false"
    smtp_use_tls = os.getenv("SMTP_USE_TLS", smtp_use_tls_default).lower() in (
        "true",
        "1",
        "yes",
    )

    print("=" * 60)
    print("🧪 SMTP Email Notification Test")
    print("=" * 60)

    # Display configuration (without password)
    print("\nSMTP Configuration:")
    print(f"  Host: {smtp_host or '[NOT SET]'}")
    print(f"  Port: {smtp_port}")
    print(f"  From: {smtp_from or '[NOT SET]'}")
    print(f"  To: {smtp_to or '[NOT SET]'}")
    print(f"  User: {smtp_user or '[NOT SET]'}")
    print(f"  Password: {'*' * len(smtp_password) if smtp_password else '[NOT SET]'}")
    print(f"  Use TLS: {smtp_use_tls} (STARTTLS)")

    # Check authentication
    smtp_auth_enabled = bool(smtp_user and smtp_password)
    if smtp_auth_enabled:
        print("  Auth: Enabled")
    else:
        print("  Auth: Disabled (no credentials provided)")

    # Host, from, and recipient are required
    if not smtp_host or not smtp_to or not smtp_from:
        print("\n❌ SMTP is not properly configured!")
        print("\nMissing required configuration:")
        if not smtp_host:
            print("  - SMTP_HOST (required)")
        if not smtp_to:
            print("  - SMTP_TO (required)")
        if not smtp_from:
            print("  - SMTP_FROM (required - set explicitly or via SMTP_USER)")
        print("\nNote: SMTP_USER and SMTP_PASSWORD are optional")
        print("      (only needed if your SMTP server requires authentication)")
        print("\nPlease configure these variables in your .env file.")
        print("See .env.example for reference.")
        return 1

    print("\n✅ SMTP configuration valid")
    print("\n📧 Sending test email...")

    # Send test notification
    test_message_id = "msg_test_smtp_123"
    test_content = """This is a test email from the Plant Care System.

If you receive this email, your SMTP configuration is working correctly!

Test Details:
- Message ID: msg_test_smtp_123
- Timestamp: Just now
- Purpose: SMTP configuration verification

You can safely ignore this message.
"""

    if _send_email_notification(
        message_id=test_message_id, content=test_content, in_reply_to=None
    ):
        print("✅ Email sent successfully!")
        print(f"\nCheck your inbox at: {smtp_to}")
        print("\nNote: It may take a few seconds to arrive.")
        print("Check spam folder if you don't see it in your inbox.")
        return 0
    else:
        print("\n❌ Failed to send email")
        print("\nCommon issues:")
        print("  - Invalid SMTP credentials")
        print("  - SMTP server unreachable")
        print("  - Firewall blocking SMTP port")
        print("  - STARTTLS not supported by server")
        print("  - App-specific password required (Gmail, Yahoo, etc.)")
        print("\nCheck the log output above for specific error details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
