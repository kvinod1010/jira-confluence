
from jira.jira_connection import JiraConnection


def get_jira_boards():

    jira = JiraConnection()

    if not jira.test_connection():
        print("Jira connection failed.")
        return

    url = f"{jira.base_url}/rest/agile/1.0/board"

    start_at = 0
    max_results = 50
    all_boards = []

    print("\nRetrieving Jira Agile boards...\n")

    try:
        while True:

            params = {
                "startAt": start_at,
                "maxResults": max_results
            }

            response = jira.session.get(
                url,
                params=params,
                timeout=30
            )

            response.raise_for_status()

            data = response.json()

            boards = data.get("values", [])
            all_boards.extend(boards)

            if data.get("isLast", True):
                break

            start_at += len(boards)

            if not boards:
                break

        print("========== JIRA AGILE BOARDS ==========\n")

        for board in all_boards:
            print(
                f"Board ID: {board.get('id')} | "
                f"Board Name: {board.get('name')} | "
                f"Type: {board.get('type')}"
            )

        print("\n=======================================")
        print(f"Total boards found: {len(all_boards)}")

    except Exception as error:
        print(f"Error retrieving Jira boards: {error}")


if __name__ == "__main__":
    get_jira_boards()
