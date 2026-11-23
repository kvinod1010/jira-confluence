
from confluence.confluence_connection import ConfluenceConnection

PAGE_ID = "730034473"

confluence = ConfluenceConnection()

url = f"{confluence.base_url}/rest/api/content/{PAGE_ID}"

response = confluence.session.get(
    url,
    params={"expand": "body.storage"},
    timeout=30
)

response.raise_for_status()

page = response.json()

storage = page["body"]["storage"]["value"]

print("\n===== CONFLUENCE RAW STORAGE FORMAT =====\n")
print(storage)

print("\n===== MARKER SEARCH =====\n")

for marker in ["RP_REPORT_START", "RP_REPORT_END"]:
    position = storage.find(marker)

    if position >= 0:
        print(f"\n{marker} FOUND:")
        print(repr(storage[max(0, position-100):position+150]))
    else:
        print(f"{marker} NOT FOUND")

