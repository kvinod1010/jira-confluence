"""
Publish selected Jira Initiative fields to an existing Confluence page.

Run from the repository root:
    python -m scripts.publish_rp_report

Existing project modules required:
    jira/jira_connection.py
    confluence/confluence_connection.py

Required Confluence page preparation:
    Add two separate paragraphs to page 730034473:
        RP_REPORT_START
        RP_REPORT_END

The script replaces only the content between those markers, preserving the
rest of the page. Test on a non-production page first if practical.

The JQL and column order below reflect the user's requested filter and screenshot.
"""

import html
import re
import sys
from datetime import datetime, timezone

from jira.jira_connection import JiraConnection
from confluence.confluence_connection import ConfluenceConnection


# ---------------------------------------------------------------------------
# Report configuration
# ---------------------------------------------------------------------------

PAGE_ID = "730034473"

JQL = (
    "issuekey in childIssuesOf(RP-12302) "
    "AND issuetype = Initiative "
    "AND resolution = unresolved "
    "AND Status != Canceled "
    'ORDER BY "Aha Rank" ASC'
)

START_MARKER = "RP_REPORT_START"
END_MARKER = "RP_REPORT_END"

# Column labels and order requested from the Jira screenshot.
REPORT_COLUMNS = [
    "Aha Rank",
    "RAG status",
    "Priority",
    "Summary",
    "Status",
    "Assignee",
    "People Leader",
    "Fix Version/s",
    "Progress",
    "Dev Complete Date",
    "Target End Date",
    "Partner Impact",
    "Functional and API Specs by",
    "Early Dev Feature Partner Drop by",
    "QA Qualified build by",
    "TOI Required",
    "TOI Target Date",
    "Assigned Team(s)",
    "Short Status",
]

# Jira system fields have stable REST field IDs.
SYSTEM_FIELD_IDS = {
    "Summary": "summary",
    "Status": "status",
    "Assignee": "assignee",
    "Priority": "priority",
    "Fix Version/s": "fixVersions",
    "Progress": "progress",
}


# ---------------------------------------------------------------------------
# Jira field discovery and extraction
# ---------------------------------------------------------------------------

def normalize_field_name(name):
    """Normalize whitespace and case for field-name matching."""
    return " ".join(str(name).strip().lower().split())


def get_report_field_ids(jira):
    """
    Discover custom field IDs by display name and map them to report columns.

    If Jira has duplicate custom field names, stop rather than silently select
    the wrong field. In that case, inspect the printed matching IDs and set an
    explicit field ID in SYSTEM_FIELD_IDS / FIELD_ID_OVERRIDES.
    """
    url = f"{jira.base_url}/rest/api/2/field"
    response = jira.session.get(url, timeout=30)
    response.raise_for_status()
    jira_fields = response.json()

    lookup = {}
    for field in jira_fields:
        name = field.get("name")
        field_id = field.get("id")
        if name and field_id:
            key = normalize_field_name(name)
            lookup.setdefault(key, []).append(field_id)

    field_ids = {}
    missing = []
    ambiguous = []

    for column in REPORT_COLUMNS:
        if column in SYSTEM_FIELD_IDS:
            field_ids[column] = SYSTEM_FIELD_IDS[column]
            continue

        matches = lookup.get(normalize_field_name(column), [])

        if len(matches) == 1:
            field_ids[column] = matches[0]
        elif len(matches) == 0:
            missing.append(column)
        else:
            ambiguous.append((column, matches))

    print("\n========== JIRA FIELD MAPPING ==========")
    for column in REPORT_COLUMNS:
        if column in field_ids:
            print(f"{column} -> {field_ids[column]}")

    if missing:
        print("\nFields not found in Jira:")
        for name in missing:
            print(f"  - {name}")

    if ambiguous:
        print("\nFields with duplicate display names:")
        for name, ids in ambiguous:
            print(f"  - {name}: {', '.join(ids)}")

    if missing or ambiguous:
        raise RuntimeError(
            "Field mapping is incomplete. Resolve the missing/ambiguous "
            "field names before publishing to Confluence."
        )

    return field_ids


def fetch_issues(jira, field_ids):
    """Run the supplied JQL and retrieve every matching issue page by page."""
    url = f"{jira.base_url}/rest/api/2/search"
    requested_fields = list(dict.fromkeys(field_ids.values()))

    start_at = 0
    page_size = 100
    all_issues = []

    while True:
        params = {
            "jql": JQL,
            "startAt": start_at,
            "maxResults": page_size,
            "fields": ",".join(requested_fields),
        }

        response = jira.session.get(
            url,
            params=params,
            timeout=60,
        )
        response.raise_for_status()

        data = response.json()
        batch = data.get("issues", [])
        all_issues.extend(batch)

        total = data.get("total", 0)
        print(f"Retrieved {len(all_issues)} of {total} matching issues.")

        if not batch or len(all_issues) >= total:
            break

        start_at += len(batch)

    return all_issues


# ---------------------------------------------------------------------------
# Jira field value formatting and Confluence table generation
# ---------------------------------------------------------------------------

def format_field_value(value, column_name=""):
    """Convert Jira REST values into readable table-cell text."""
    if value is None:
        return ""

    if column_name == "Progress" and isinstance(value, dict):
        total = value.get("total", 0) or 0
        completed = value.get("completed", 0) or 0
        if total:
            return f"{completed * 100 / total:.0f}%"
        return "0%"

    if isinstance(value, dict):
        # Jira user, status, priority, option, version and similar objects.
        for key in (
            "displayName",
            "name",
            "value",
            "key",
            "emailAddress",
        ):
            if value.get(key) not in (None, ""):
                return str(value[key])

        # Fallback for other structured values.
        return "; ".join(
            f"{key}: {format_field_value(item)}"
            for key, item in value.items()
            if item not in (None, "")
        )

    if isinstance(value, list):
        return ", ".join(
            format_field_value(item, column_name)
            for item in value
            if item is not None
        )

    if isinstance(value, bool):
        return "Yes" if value else "No"

    return str(value)


def build_confluence_table(issues, field_ids):
    """Create a Confluence storage-format XHTML table in requested column order."""
    header_cells = "".join(
        f"<th><p>{html.escape(column)}</p></th>"
        for column in REPORT_COLUMNS
    )

    rows = []

    for issue in issues:
        issue_fields = issue.get("fields", {})
        cells = []

        for column in REPORT_COLUMNS:
            jira_field_id = field_ids[column]
            raw_value = issue_fields.get(jira_field_id)
            display_value = format_field_value(raw_value, column)
            cells.append(
                f"<td><p>{html.escape(display_value)}</p></td>"
            )

        rows.append("<tr>" + "".join(cells) + "</tr>")

    if not rows:
        rows.append(
            f'<tr><td colspan="{len(REPORT_COLUMNS)}">'
            "<p>No matching issues found.</p></td></tr>"
        )

    refreshed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    refresh_note = (
        f"<p><em>Last refreshed: {refreshed_at} | "
        f"Matching Initiatives: {len(issues)}</em></p>"
    )

    return (
        refresh_note
        + "<table><tbody>"
        + f"<tr>{header_cells}</tr>"
        + "".join(rows)
        + "</tbody></table>"
    )


# ---------------------------------------------------------------------------
# Confluence page update
# ---------------------------------------------------------------------------

def replace_marked_section(storage_value, table_markup):
    """
    Replace only the section between the two marker paragraphs.

    The markers must each be in their own paragraph in Confluence storage.
    """
    pattern = (
        rf"(<p[^>]*>\s*{re.escape(START_MARKER)}\s*</p>)"
        rf".*?"
        rf"(<p[^>]*>\s*{re.escape(END_MARKER)}\s*</p>)"
    )

    updated_storage, replacements = re.subn(
        pattern,
        lambda match: match.group(1) + table_markup + match.group(2),
        storage_value,
        count=1,
        flags=re.DOTALL,
    )

    if replacements != 1:
        raise RuntimeError(
            "Could not find the report markers in the Confluence page. "
            f"Add two separate paragraphs containing exactly "
            f"{START_MARKER} and {END_MARKER}, with START above END."
        )

    return updated_storage


def update_confluence_page(confluence, table_markup):
    """Read the existing page and publish a new version preserving other content."""
    page_url = f"{confluence.base_url}/rest/api/content/{PAGE_ID}"

    response = confluence.session.get(
        page_url,
        params={"expand": "body.storage,version,space"},
        timeout=30,
    )
    response.raise_for_status()
    page = response.json()

    current_storage = page["body"]["storage"]["value"]
    new_storage = replace_marked_section(current_storage, table_markup)

    current_version = page["version"]["number"]

    payload = {
        "id": page["id"],
        "type": page["type"],
        "title": page["title"],
        "space": {"key": page["space"]["key"]},
        "version": {
            "number": current_version + 1,
            "message": "Refresh RP Initiative report from Jira automation",
        },
        "body": {
            "storage": {
                "value": new_storage,
                "representation": "storage",
            }
        },
    }

    update_response = confluence.session.put(
        page_url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    update_response.raise_for_status()

    updated_page = update_response.json()
    new_version = updated_page.get("version", {}).get("number")
    print(
        f"SUCCESS: Updated Confluence page '{updated_page.get('title')}' "
        f"to version {new_version}."
    )
    print(f"Confluence page ID: {PAGE_ID}")


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def main():
    print("Connecting to Jira...")
    jira = JiraConnection()

    if not jira.test_connection():
        raise RuntimeError("Jira connection test failed.")

    print("\nDiscovering Jira fields required for the report...")
    field_ids = get_report_field_ids(jira)

    print("\nExecuting JQL and retrieving matching Initiatives...")
    issues = fetch_issues(jira, field_ids)
    print(f"\nTotal matching Initiatives: {len(issues)}")

    print("\nConnecting to Confluence...")
    confluence = ConfluenceConnection()

    if not confluence.test_connection():
        raise RuntimeError("Confluence connection test failed.")

    print("\nBuilding the selected-column Confluence table...")
    table_markup = build_confluence_table(issues, field_ids)

    print("\nUpdating the designated section of the Confluence page...")
    update_confluence_page(confluence, table_markup)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nERROR: {error}")
        sys.exit(1)
