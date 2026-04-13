"""Generate Google Ads OAuth2 Refresh Token.

Usage:
  cd backend && python -m scripts.google_auth

Steps:
  1. Script opens browser for Google login
  2. You authorize the app
  3. Copy the authorization code from the redirect URL
  4. Paste it here -> script exchanges for refresh_token
  5. Add refresh_token to .env
"""

import os
import sys
import webbrowser
from urllib.parse import urlencode

# Your OAuth2 credentials — set these as env vars or paste here temporarily
CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"  # For desktop apps
SCOPE = "https://www.googleapis.com/auth/adwords"


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Error: Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET env vars")
        sys.exit(1)

    # Step 1: Generate authorization URL
    auth_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"https://accounts.google.com/o/oauth2/auth?{urlencode(auth_params)}"

    print("=" * 60)
    print("  Google Ads OAuth2 - Generate Refresh Token")
    print("=" * 60)
    print()
    print("Opening browser for Google authorization...")
    print()
    print("If browser doesn't open, copy this URL manually:")
    print()
    print(auth_url)
    print()

    webbrowser.open(auth_url)

    # Step 2: Get authorization code
    print("-" * 60)
    auth_code = input("Paste the authorization code here: ").strip()

    if not auth_code:
        print("No code provided. Exiting.")
        sys.exit(1)

    # Step 3: Exchange code for tokens
    import json
    from urllib.request import Request, urlopen
    from urllib.parse import urlencode as ue

    token_data = ue({
        "code": auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    req = Request(
        "https://oauth2.googleapis.com/token",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urlopen(req) as resp:
            result = json.loads(resp.read().decode())

        refresh_token = result.get("refresh_token")
        access_token = result.get("access_token")

        print()
        print("=" * 60)
        print("  SUCCESS!")
        print("=" * 60)
        print()
        print(f"Refresh Token: {refresh_token}")
        print()
        print("Add this to your .env file:")
        print(f"  GOOGLE_REFRESH_TOKEN={refresh_token}")
        print()
        if access_token:
            print(f"(Access Token: {access_token[:30]}... - expires in {result.get('expires_in', '?')}s)")
        print()
        print("You also need:")
        print("  GOOGLE_DEVELOPER_TOKEN=<from Google Ads API Center>")
        print("  GOOGLE_LOGIN_CUSTOMER_ID=<your MCC account ID, e.g. 123-456-7890>")

    except Exception as e:
        print(f"\nError exchanging code: {e}")
        # Try to read error response
        if hasattr(e, 'read'):
            print(e.read().decode())
        sys.exit(1)


if __name__ == "__main__":
    main()
