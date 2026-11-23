"""
Publish selected Jira Initiative fields to Confluence page 730034473.

Run from the repository root:
    python -m scripts.publish_rp_report

Requires existing jira/jira_connection.py and
confluence/confluence_connection.py modules.

The Confluence page must contain two separate normal paragraphs:
RP_REPORT_START
RP_REPORT_END

Only the content between those markers is replaced.
Short Status is rendered as an Expand macro titled "Status".
RAG status cells are filled Amber, Green, or Red; blank/other values
are left unfilled.
"""

import html
import re
import sys
from datetime import datetime, timezone

from jira.jira_connection import JiraConnection
from confluence.confluence_connection import ConfluenceConnection


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

SYSTEM_FIELD_IDS = {
    "Summary": "summary",
    "Status": "status",
    "Assignee": "assignee",
    "Priority": "priority",
    "Fix Version/s": "fixVersions",
    "Progress": "progress",
}

RAG_COLORS = {
    "amber": "#FFC000",
    "green": "#70AD47",
    "red": "#FF0000",
}


def normalize_field_name(name):
    return " ".join(str(name).strip().lower().split())


def get_report_field_ids(jira):
    """Discover Jira custom field IDs by their display names."""
    response = jira.session.get(
        f"{jira.base_url}/rest/api/2/field", timeout=30
    )
    response.raise_for_status()

    lookup = {}
    for field in response.json():
        name, field_id = field.get("name"), field.get("id")
        if name and field_id:
            lookup.setdefault(normalize_field_name(name), []).append(field_id)

    field_ids, missing, ambiguous = {}, [], []

    for column in REPORT_COLUMNS:
        if column in SYSTEM_FIELD_IDS:
            field_ids[column] = SYSTEM_FIELD_IDS[column]
            continue

        matches = lookup.get(normalize_field_name(column), [])
        if len(matches) == 1:
            field_ids[column] = matches[0]
        elif not matches:
            missing.append(column)
        else:
            ambiguous.append((column, matches))

    print("\n========== JIRA FIELD MAPPING ==========")
    for column in REPORT_COLUMNS:
        if column in field_ids:
            print(f"{column} -> {field_ids[column]}")

    if missing:
        print("\nFields not found:")
        for name in missing:
            print(f"  - {name}")

    if ambiguous:
        print("\nFields with duplicate names:")
        for name, ids in ambiguous:
            print(f"  - {name}: {', '.join(ids)}")

    if missing or ambiguous:
        raise RuntimeError(
            "Field mapping incomplete. Resolve missing or duplicate field "
            "names before publishing."
        )
    return field_ids


def fetch_issues(jira, field_ids):
    """Run JQL and retrieve all matching issues with pagination."""
    url = f"{jira.base_url}/rest/api/2/search"
    requested_fields = list(dict.fromkeys(field_ids.values()))
    start_at, page_size, all_issues = 0, 100, []

    while True:
        response = jira.session.get(
            url,
            params={
                "jql": JQL,
                "startAt": start_at,
                "maxResults": page_size,
                "fields": ",".join(requested_fields),
            },
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


def format_field_value(value, column_name=""):
    """Convert Jira REST values into readable text."""
    if value is None:
        return ""

    if column_name == "Progress" and isinstance(value, dict):
        total = value.get("total", 0) or 0
        completed = value.get("completed", 0) or 0
        return f"{completed * 100 / total:.0f}%" if total else "0%"

    if isinstance(value, dict):
        for key in ("displayName", "name", "value", "key", "emailAddress"):
            if value.get(key) not in (None, ""):
                return str(value[key])
        return "; ".join(
            f"{key}: {format_field_value(item)}"
            for key, item in value.items()
            if item not in (None, "")
        )

    if isinstance(value, list):
        return ", ".join(
            format_field_value(item, column_name)
            for item in value if item is not None
        )

    if isinstance(value, bool):
        return "Yes" if value else "No"

    return str(value)


def make_expand_macro(text_value, title="Status"):
    """Create a Confluence Expand macro for the Short Status cell."""
    safe_text = html.escape(text_value)
    if not safe_text.strip():
        safe_text = "No short status provided."

    return (
        '<ac:structured-macro ac:name="expand">'
        f'<ac:parameter ac:name="title">{html.escape(title)}</ac:parameter>'
        '<ac:rich-text-body>'
        f'<p>{safe_text}</p>'
        '</ac:rich-text-body>'
        '</ac:structured-macro>'
    )


def make_rag_cell(text_value):
    """
    Create a filled RAG cell for Amber/Green/Red.
    Blank or unrecognized values remain unfilled.
    """
    display_value = (text_value or "").strip()
    if not display_value:
        return "<td><p></p></td>"

    fill_color = RAG_COLORS.get(display_value.casefold())
    safe_value = html.escape(display_value)

    if fill_color:
        return (
            f'<td style="background-color: {fill_color};">'
            f"<p><strong>{safe_value}</strong></p></td>"
        )

    return f"<td><p>{safe_value}</p></td>"


def build_confluence_table(issues, field_ids):
    """Build table in the exact requested column order."""
    headers = "".join(
        f"<th><p>{html.escape(column)}</p></th>"
        for column in REPORT_COLUMNS
    )
    rows = []

    for issue in issues:
        issue_fields = issue.get("fields", {})
        cells = []

        for column in REPORT_COLUMNS:
            raw_value = issue_fields.get(field_ids[column])
            display_value = format_field_value(raw_value, column)

            if column == "Short Status":
                cells.append(
                    f"<td>{make_expand_macro(display_value, title='Status')}</td>"
                )
            elif column == "RAG status":
                cells.append(make_rag_cell(display_value))
            else:
                cells.append(
                    f"<td><p>{html.escape(display_value)}</p></td>"
                )

        rows.append("<tr>" + "".join(cells) + "</tr>")

    if not rows:
        rows.append(
            f'<tr><td colspan="{len(REPORT_COLUMNS)}">'
            "<p>No matching issues found.</p></td></tr>"
        )

    refreshed = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    note = (
        f"<p><em>Last refreshed: {refreshed} | "
        f"Matching Initiatives: {len(issues)}</em></p>"
    )
    return note + (
        "<table><tbody><tr>" + headers + "</tr>"
        + "".join(rows) + "</tbody></table>"
    )


def replace_marked_section(storage_value, table_markup):
    """Replace only the content between the marker paragraphs."""
    pattern = (
        rf"(<p[^>]*>\s*{re.escape(START_MARKER)}\s*</p>)"
        rf".*?"
        rf"(<p[^>]*>\s*{re.escape(END_MARKER)}\s*</p>)"
    )
    updated, count = re.subn(
        pattern,
        lambda match: match.group(1) + table_markup + match.group(2),
        storage_value,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError(
            "Could not find report markers. Add RP_REPORT_START and "
            "RP_REPORT_END as separate normal paragraphs, not code text."
        )
    return updated


def update_confluence_page(confluence, table_markup):
    """Update the page while preserving content outside report markers."""
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

    result = confluence.session.put(
        page_url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    result.raise_for_status()
    updated_page = result.json()
    version = updated_page.get("version", {}).get("number")
    print(
        f"SUCCESS: Updated '{updated_page.get('title')}' "
        f"to version {version}."
    )
    print(f"Confluence page ID: {PAGE_ID}")


def main():
    print("Connecting to Jira...")
    jira = JiraConnection()
    if not jira.test_connection():
        raise RuntimeError("Jira connection test failed.")

    print("\nDiscovering Jira report fields...")
    field_ids = get_report_field_ids(jira)

    print("\nExecuting JQL and retrieving Initiatives...")
    issues = fetch_issues(jira, field_ids)
    print(f"Total matching Initiatives: {len(issues)}")

    print("\nConnecting to Confluence...")
    confluence = ConfluenceConnection()
    if not confluence.test_connection():
        raise RuntimeError("Confluence connection test failed.")

    print("\nBuilding selected-column Confluence table...")
    table_markup = build_confluence_table(issues, field_ids)

    print("\nUpdating Confluence report section...")
    update_confluence_page(confluence, table_markup)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nERROR: {error}")
        sys.exit(1)
