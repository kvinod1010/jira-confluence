"""
Reusable Confluence connectivity and authentication check.

Install in your active virtual environment:
    python -m pip install requests python-dotenv truststore

Add to the project-root .env:
    CONFLUENCE_URL=https://confluence.storage.hpecorp.net
    CONFLUENCE_AUTH_TYPE=bearer
    CONFLUENCE_API_TOKEN=your_approved_confluence_token

If your Confluence administrator confirms Basic authentication is supported:
    CONFLUENCE_AUTH_TYPE=basic
    CONFLUENCE_USERNAME=your_username
    CONFLUENCE_PASSWORD=your_password

Run from the project root:
    python -m confluence.confluence_connection

Uses the Windows native certificate store through truststore.
TLS certificate verification remains enabled.
"""

import truststore

# Call before importing requests.
truststore.inject_into_ssl()

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class ConfluenceConnection:
    """Create and test an authenticated connection to Confluence."""

    def __init__(self, timeout: int = 20):
        self.base_url = os.getenv("CONFLUENCE_URL", "").strip().rstrip("/")
        self.auth_type = os.getenv(
            "CONFLUENCE_AUTH_TYPE", "bearer"
        ).strip().lower()
        self.timeout = timeout

        if not self.base_url:
            raise ValueError(
                "CONFLUENCE_URL is missing. Use the site root URL, "
                "not a /spaces/... page URL."
            )

        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

        if self.auth_type == "bearer":
            token = os.getenv("CONFLUENCE_API_TOKEN", "").strip()
            if not token:
                raise ValueError(
                    "CONFLUENCE_API_TOKEN is missing from the .env file."
                )
            self.session.headers["Authorization"] = f"Bearer {token}"

        elif self.auth_type == "basic":
            username = os.getenv("CONFLUENCE_USERNAME", "").strip()
            password = os.getenv("CONFLUENCE_PASSWORD", "")
            if not username or not password:
                raise ValueError(
                    "CONFLUENCE_USERNAME or CONFLUENCE_PASSWORD is missing."
                )
            self.session.auth = HTTPBasicAuth(username, password)

        else:
            raise ValueError(
                "CONFLUENCE_AUTH_TYPE must be 'bearer' or 'basic'."
            )

    def test_connection(self) -> bool:
        """Call Confluence's current-user REST endpoint."""
        endpoint = f"{self.base_url}/rest/api/user/current"
        print(f"Testing Confluence connection: {self.base_url}")

        try:
            response = self.session.get(endpoint, timeout=self.timeout)

            if response.status_code == 200:
                user_data = response.json()
                display_name = (
                    user_data.get("displayName")
                    or user_data.get("username")
                    or user_data.get("userKey")
                    or "Authenticated user"
                )
                print(
                    "SUCCESS: Confluence connection and authentication "
                    "are working."
                )
                print(f"Authenticated as: {display_name}")
                return True

            if response.status_code == 401:
                print(
                    "AUTHENTICATION ERROR: HTTP 401. Check the Confluence "
                    "token/credentials and supported authentication method."
                )
            elif response.status_code == 403:
                print(
                    "ACCESS ERROR: HTTP 403. Your account may not have "
                    "permission to access this REST endpoint."
                )
            elif response.status_code == 404:
                print(
                    "ENDPOINT NOT FOUND: HTTP 404. Verify CONFLUENCE_URL "
                    "and whether this REST endpoint is available."
                )
            else:
                print(
                    f"CONFLUENCE RESPONSE: HTTP {response.status_code}. "
                    "Check the URL, API availability, and permissions."
                )

            print(f"Response: {response.text[:500]}")
            return False

        except requests.exceptions.SSLError as error:
            print(f"SSL CERTIFICATE ERROR: {error}")
            print("Do not disable SSL verification.")
        except requests.exceptions.Timeout:
            print("TIMEOUT: Check network/VPN access and Confluence availability.")
        except requests.exceptions.ConnectionError as error:
            print(f"CONNECTION ERROR: Could not reach Confluence: {error}")
        except requests.exceptions.RequestException as error:
            print(f"REQUEST ERROR: {error}")
        except ValueError as error:
            print(f"INVALID RESPONSE: {error}")

        return False


if __name__ == "__main__":
    try:
        confluence = ConfluenceConnection()
        sys.exit(0 if confluence.test_connection() else 1)
    except ValueError as error:
        print(f"CONFIGURATION ERROR: {error}")
        sys.exit(1)
