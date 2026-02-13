#!/usr/bin/env python3
"""Reset VPS Administrator password via ConoHa OpenStack API.

Usage:
    python3 deploy/conoha-reset-password.py \
        --api-user <APIユーザー名> \
        --api-password <APIパスワード> \
        --tenant-id <テナントID> \
        --new-password <新パスワード>

The server ID defaults to the known ConoHa VPS instance.
Override with --server-id if needed.
"""
import argparse
import json
import ssl
import sys
import urllib.request
import urllib.error

# macOS Python may lack default CA certs; use certifi if available
try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()
    # Fallback: if default context also fails, disable verification with warning
    try:
        urllib.request.urlopen("https://identity.c3j1.conoha.io", timeout=5, context=_SSL_CONTEXT)
    except Exception:
        print("WARNING: SSL certificate verification disabled (install certifi to fix)")
        _SSL_CONTEXT = ssl._create_unverified_context()

IDENTITY_URL = "https://identity.c3j1.conoha.io/v3/auth/tokens"
COMPUTE_BASE = "https://compute.c3j1.conoha.io/v2.1/servers"
DEFAULT_SERVER_ID = "80348600-9aec-4fe2-bd5d-dbad239fbff8"


def get_token(api_user: str, api_password: str, tenant_id: str) -> str:
    """Authenticate with ConoHa Identity API and return an auth token."""
    payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "id": api_user,
                        "password": api_password,
                    }
                },
            },
            "scope": {
                "project": {
                    "id": tenant_id,
                }
            },
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        IDENTITY_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=_SSL_CONTEXT) as resp:
            token = resp.headers.get("X-Subject-Token")
            if not token:
                print("ERROR: Token not found in response headers")
                sys.exit(1)
            return token
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"ERROR: Authentication failed (HTTP {e.code})")
        print(f"Response: {body}")
        sys.exit(1)


def change_password(token: str, server_id: str, new_password: str) -> None:
    """Send changePassword action to the Compute API."""
    url = f"{COMPUTE_BASE}/{server_id}/action"
    payload = {"changePassword": {"adminPass": new_password}}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Auth-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=_SSL_CONTEXT) as resp:
            print(f"SUCCESS: Password change accepted (HTTP {resp.status})")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 501:
            print("ERROR: changePassword is not supported by this provider.")
            print("Alternative: Use ConoHa control panel to rebuild the server,")
            print("or contact ConoHa support for password reset assistance.")
        elif e.code == 409:
            print("ERROR: Server is in a conflicting state (may be rebuilding).")
            print("Wait a few minutes and try again.")
        else:
            print(f"ERROR: Password change failed (HTTP {e.code})")
        print(f"Response: {body}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset ConoHa VPS Administrator password via OpenStack API"
    )
    parser.add_argument("--api-user", required=True, help="ConoHa API username")
    parser.add_argument("--api-password", required=True, help="ConoHa API password")
    parser.add_argument("--tenant-id", required=True, help="ConoHa tenant ID")
    parser.add_argument("--new-password", required=True, help="New Administrator password")
    parser.add_argument(
        "--server-id",
        default=DEFAULT_SERVER_ID,
        help=f"Server UUID (default: {DEFAULT_SERVER_ID})",
    )
    args = parser.parse_args()

    if len(args.new_password) < 8:
        print("ERROR: Password must be at least 8 characters")
        sys.exit(1)

    print(f"Authenticating as {args.api_user}...")
    token = get_token(args.api_user, args.api_password, args.tenant_id)
    print("Authentication successful.")

    print(f"Changing password for server {args.server_id}...")
    change_password(token, args.server_id, args.new_password)
    print("Done. Try RDP login with the new password.")


if __name__ == "__main__":
    main()
