
from jira.jira_connection import JiraConnection

def get_jira_projects():

    jira = JiraConnection()

    if not jira.test_connection():
        print("Jira connection failed.")
        return

    url = f"{jira.base_url}/rest/api/2/project"

    try:
        response = jira.session.get(
            url,
            timeout=20
        )

        response.raise_for_status()

        projects = response.json()

        print("\n===== JIRA PROJECTS =====\n")

        for project in projects:
            print(
                f"Project: {project.get('name')} | "
                f"Key: {project.get('key')}"
            )

        print(f"\nTotal projects found: {len(projects)}")

    except Exception as error:
        print(f"Error retrieving projects: {error}")


if __name__ == "__main__":
    get_jira_projects()
