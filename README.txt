HPE Sprint Automation - Jira connection starter

1. Copy this folder to a local development location.
2. Rename .env.example to .env.
3. Fill in the authentication settings approved for your HPE Jira account.
4. Open a terminal in this folder and run:
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
5. Run:
   python -m jira.jira_connection

The module can also be imported by other Python scripts:
   from jira.jira_connection import JiraConnection
   jira = JiraConnection()
   jira.test_connection()

Never commit .env or share your token/password. Follow HPE IT/security guidance for approved Jira API authentication. Do not disable TLS certificate verification.
