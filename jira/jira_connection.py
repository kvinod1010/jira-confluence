"""
Reusable Jira connectivity and authentication check.

Setup:
1. Install dependencies: pip install requests python-dotenv
2. Create a .env file in the project root (the parent folder of this file):
   JIRA_URL=https://jira.storage.hpecorp.net
   JIRA_AUTH_TYPE=bearer
   JIRA_API_TOKEN=your_personal_access_token

   For username/password authentication instead:
   JIRA_AUTH_TYPE=basic
   JIRA_USERNAME=your_username
   JIRA_PASSWORD=your_password

Run:
   python jira_connection.py

You can also import JiraConnection from another Python file:
   from jira_connection import JiraConnection
   jira = JiraConnection()
   result = jira.test_connection()
"""

import truststore

# Use Windows native certificate store
truststore.inject_into_ssl()

import os
import sys
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth


# Load .env from the project root (one level above this jira folder).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class JiraConnection:
    """Create and test an authenticated connection to Jira Server/Data Center."""

    def __init__(self, timeout: int = 20):
        self.base_url = os.getenv("JIRA_URL", "").strip().rstrip("/")
        self.auth_type = os.getenv("JIRA_AUTH_TYPE", "bearer").strip().lower()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

        if not self.base_url:
            raise ValueError("JIRA_URL is missing. Add it to the project .env file.")

        if self.auth_type == "bearer":
            token = os.getenv("JIRA_API_TOKEN", "").strip()
            if not token:
                raise ValueError("JIRA_API_TOKEN is missing from the .env file.")
            self.session.headers["Authorization"] = f"Bearer {token}"

        elif self.auth_type == "basic":
            username = os.getenv("JIRA_USERNAME", "").strip()
            password = os.getenv("JIRA_PASSWORD", "")
            if not username or not password:
                raise ValueError(
                    "JIRA_USERNAME or JIRA_PASSWORD is missing from the .env file."
                )
            self.session.auth = HTTPBasicAuth(username, password)

        else:
            raise ValueError("JIRA_AUTH_TYPE must be 'bearer' or 'basic'.")

    def test_connection(self) -> bool:
        """Call Jira's current-user REST endpoint and return True on success."""
        endpoint = f"{self.base_url}/rest/api/2/myself"

        print(f"Testing Jira connection: {self.base_url}")

        try:
            response = self.session.get(endpoint, timeout=self.timeout)

            if response.status_code == 200:
                user_data = response.json()
                display_name = user_data.get("displayName", "Authenticated user")
                print("SUCCESS: Jira connection and authentication are working.")
                print(f"Authenticated as: {display_name}")
                return True

            if response.status_code in (401, 403):
                print(
                    f"AUTHENTICATION/ACCESS ERROR: HTTP {response.status_code}. "
                    "Check your token or credentials and Jira API permissions."
                )
            else:
                print(
                    f"JIRA RESPONSE: HTTP {response.status_code}. "
                    "Check the Jira URL, API availability, and access permissions."
                )

            print(f"Response: {response.text[:500]}")
            return False

        except requests.exceptions.SSLError as error:
            print(f"SSL CERTIFICATE ERROR: {error}")
            print("Do not disable SSL verification as a workaround. Contact HPE IT if needed.")
        except requests.exceptions.Timeout:
            print("TIMEOUT: Jira did not respond within the configured time.")
            print("Check VPN, network access, and the Jira service.")
        except requests.exceptions.ConnectionError as error:
            print(f"CONNECTION ERROR: Could not reach Jira: {error}")
            print("Check your network/VPN and whether the Jira URL is reachable.")
        except requests.exceptions.RequestException as error:
            print(f"REQUEST ERROR: {error}")
        except ValueError as error:
            print(f"CONFIGURATION ERROR: {error}")

        return False


if __name__ == "__main__":
    try:
        jira = JiraConnection()
        success = jira.test_connection()
        sys.exit(0 if success else 1)
    except ValueError as error:
        print(f"CONFIGURATION ERROR: {error}")
        sys.exit(1)
