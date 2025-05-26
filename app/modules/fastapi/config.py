import os
from dotenv import load_dotenv

load_dotenv()

JIRA_CLIENT_ID = os.getenv("JIRA_CLIENT_ID")
JIRA_CLIENT_SECRET = os.getenv("JIRA_CLIENT_SECRET")
REDIRECT_URI = os.getenv("JIRA_REDIRECT_URI")
SCOPES = os.getenv("JIRA_SCOPES")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def get_jira_auth_url(telegram_id: int):
    return (
        f"https://auth.atlassian.com/authorize?"
        f"audience=api.atlassian.com&client_id={JIRA_CLIENT_ID}&"
        f"scope={SCOPES}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"state={telegram_id}&"
        f"response_type=code&prompt=consent"
    )