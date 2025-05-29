from atlassian import Jira
import requests
from datetime import datetime
import pytz
import unicodedata

def get_jira_client(access_token: str, cloud_id: str) -> Jira:
    """
    Tạo đối tượng Jira client dùng access_token Bearer OAuth 2.0.
    atlassian-python-api chưa hỗ trợ trực tiếp OAuth2 bearer token,
    nên cần khởi tạo session có header Authorization rồi truyền vào Jira(client=session).
    """
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    })

    base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}"
    # Khởi tạo Jira client với base_url + session tùy chỉnh
    return Jira(
        url=base_url,
        session=session,
        cloud=True 
    )


def get_current_user(jira: Jira):
    response = jira.session.get(f"{jira.url}/rest/api/3/myself")
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to get current user: {response.status_code} {response.text}")


def get_all_issues(access_token, cloud_id):
    jira = get_jira_client(access_token, cloud_id)
    account_id = get_current_user(jira)["accountId"]
    jql = f'assignee = {account_id} AND statusCategory != Done ORDER BY updated DESC'
    issues = jira.jql(jql)["issues"]
    
    formatted_issues = []
    for issue in issues:
        fields = issue["fields"]
        formatted_issues.append({
            "key": issue.get("key"),
            "summary": fields.get("summary"),
            "status": fields["status"].get("name"),
            "deadline": fields.get("duedate")
        })
    return formatted_issues


def get_today_issues(access_token, cloud_id):
    jira = get_jira_client(access_token, cloud_id)
    account_id = get_current_user(jira)["accountId"]
    
    tz_hn = pytz.timezone("Asia/Ho_Chi_Minh")
    today_hn = datetime.now(tz_hn).strftime("%Y-%m-%d")
    
    jql = (
        f'assignee = {account_id} AND '
        f'statusCategory != Done AND '
        f'duedate >= "{today_hn}" '
        f'ORDER BY duedate ASC'
    )
    
    issues = jira.jql(jql)["issues"]
    
    formatted_issues = []
    for issue in issues:
        formatted_issues.append({
            "key": issue.get("key"),
            "summary": issue["fields"].get("summary"),
            "status": issue["fields"]["status"].get("name"),
            "deadline": issue["fields"].get("duedate")
        })
    return formatted_issues


def get_issue_detail(access_token, cloud_id, issue_key):
    jira = get_jira_client(access_token, cloud_id)
    issue = jira.issue(issue_key)
    fields = issue["fields"]

    return {
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "description": fields.get("description"),
        "status": fields["status"].get("name") if fields.get("status") else None,
        "assignee": fields["assignee"]["displayName"] if fields.get("assignee") else None,
        "reporter": fields["reporter"]["displayName"] if fields.get("reporter") else None,
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "duedate": fields.get("duedate"),
        "priority": fields["priority"]["name"] if fields.get("priority") else None,
        "project": fields["project"]["key"] if fields.get("project") else None
    }

def format_started(user_input: str, tz='Asia/Ho_Chi_Minh'):
    dt = datetime.strptime(user_input, "%Y-%m-%d %H:%M")
    
    timezone = pytz.timezone(tz)
    dt = timezone.localize(dt)
    
    return dt.strftime('%Y-%m-%dT%H:%M:%S.000%z')

def log_work(access_token, cloud_id, issue_key, date, time_spend, comment):
    jira = get_jira_client(access_token, cloud_id)
    started = format_started(date)
    jira.issue_worklog(issue_key, started, time_spend*60, comment)

    return {
        "issue_key": issue_key,
        "started": started,
        "time_spend": time_spend,
        "comment": comment
    }

# def get_account_id(email, access_token, cloud_id):
#     url = f"https://api.atlassian.com/ex/jira/{cloud_id}.atlassian.net/rest/api/3/user/search?query={email}"
#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "Accept": "application/json"
#     }
#     response = requests.get(url, headers=headers)
#     users = response.json()
#     if users:
#         return users[0].get("accountId")
#     return None

def normalize(text):
    if not text:
        return ""
    return unicodedata.normalize("NFKD", text).casefold().strip()

def get_account_id(jira, project_key, assignee_email=None, assignee_displayname=None):
    users = jira.get_all_assignable_users_for_project(project_key, start=0, limit=100)

    for user in users:
        display_name = user.get("displayName", "")
        email = user.get("emailAddress", "")
        account_id = user.get("accountId")

        if assignee_email and email and normalize(email) == normalize(assignee_email):
            return account_id

        if assignee_displayname and normalize(display_name) == normalize(assignee_displayname):
            return account_id

    return None

def create_issue(access_token, cloud_id, domain, project_key, summary, description, issue_type="Task", assignee_displayname=None, assignee_email=None):
    jira = get_jira_client(access_token, cloud_id)
    
    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "description": description,
        "issuetype": {"name": issue_type}
    }
    
    assignee_id = None
    if assignee_email or assignee_displayname:
        assignee_id = get_account_id(jira, project_key, assignee_email, assignee_displayname)

    if assignee_id:
        fields["assignee"] = {"accountId": assignee_id}

    issue = jira.create_issue(fields=fields)
    
    return {
        "issue_id": issue.get("id", None),
        "issue_key": issue.get("key", None),
        "issue_url": f"https://{domain}.atlassian.net/browse/{issue.get('key', '')}",
        "summary": summary,
        "assignee_id": assignee_id,
        "assignee_displayname": assignee_displayname,
        "issue_type": issue_type,
        "description": description,
    }

def transition_issue(access_token, cloud_id, issue_key, transition_name):
    jira = get_jira_client(access_token, cloud_id)
    
    jira.set_issue_status(issue_key, transition_name)
    
    new_status = jira.get_issue_status(issue_key)
    issue = jira.issue(issue_key)
    summary = issue.get('fields', {}).get('summary')
    assignee = issue.get('fields', {}).get('assignee')
    assignee_name = assignee.get('displayName') if assignee else None
    
    return {
        "issue_key": issue_key,
        "status": new_status,
        "summary": summary,
        "assignee": assignee_name,
    }

def main():
    access_token = "eyJraWQiOiJhdXRoLmF0bGFzc2lhbi5jb20tQUNDRVNTLTk0ZTczYTkwLTUxYWQtNGFjMS1hOWFjLWU4NGUwNDVjNDU3ZCIsImFsZyI6IlJTMjU2In0.eyJqdGkiOiJlYWMxOTNmOC1kZTFiLTRhZjctYWNhYi05ZjJlODA5OThjMjUiLCJzdWIiOiI3MTIwMjA6YjZkMTIyYzgtNWY2OC00N2EzLTkwMjUtMTQ4NDc5MTBkNTE4IiwibmJmIjoxNzQ4NTMxMTg0LCJpc3MiOiJodHRwczovL2F1dGguYXRsYXNzaWFuLmNvbSIsImlhdCI6MTc0ODUzMTE4NCwiZXhwIjoxNzQ4NTM0Nzg0LCJhdWQiOiJ0VWc5VGpqYTRTSmEwTld5M0tBUGNjQXI0M3BiZGNIdSIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS9yZWZyZXNoX2NoYWluX2lkIjoidFVnOVRqamE0U0phME5XeTNLQVBjY0FyNDNwYmRjSHUtNzEyMDIwOmI2ZDEyMmM4LTVmNjgtNDdhMy05MDI1LTE0ODQ3OTEwZDUxOC03NDJjNzQzMC1lYjg0LTQxZDItYjE5Mi1jZDg1MzVhZjBhZDIiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vcnRpIjoiMGFmODYyNDItN2E0OC00MGM0LTg3YTMtMGY3MmU2MjA4YzY3IiwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL3VqdCI6IjA3OGQ5NTc2LTUyMTgtNGM2Yi1iZWFiLTVmNTE0ZDE3OGExOSIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS9hdGxfdG9rZW5fdHlwZSI6IkFDQ0VTUyIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS9zZXNzaW9uX2lkIjoiNmY0NDI0OWEtODczYS00ZmU4LTljMjUtYTMwNzFjYTBhM2Y0IiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL2ZpcnN0UGFydHkiOmZhbHNlLCJodHRwczovL2F0bGFzc2lhbi5jb20vdmVyaWZpZWQiOnRydWUsImNsaWVudF9pZCI6InRVZzlUamphNFNKYTBOV3kzS0FQY2NBcjQzcGJkY0h1Iiwic2NvcGUiOiJtYW5hZ2U6amlyYS1wcm9qZWN0IG9mZmxpbmVfYWNjZXNzIHJlYWQ6YWNjb3VudCByZWFkOmppcmEtdXNlciByZWFkOmppcmEtd29yayByZWFkOm1lIHdyaXRlOmppcmEtd29yayIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS9wcm9jZXNzUmVnaW9uIjoidXMtd2VzdC0yIiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL2VtYWlsRG9tYWluIjoiZ21haWwuY29tIiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL3N5c3RlbUFjY291bnRFbWFpbCI6Ijc2MzNlMzQyLWM0YzctNGFmMS04NDU0LTMzMjMwYTE1ZTM0NUBjb25uZWN0LmF0bGFzc2lhbi5jb20iLCJodHRwczovL2F0bGFzc2lhbi5jb20vM2xvIjp0cnVlLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vdmVyaWZpZWQiOnRydWUsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9vYXV0aENsaWVudElkIjoidFVnOVRqamE0U0phME5XeTNLQVBjY0FyNDNwYmRjSHUiLCJodHRwczovL2F0bGFzc2lhbi5jb20vc3lzdGVtQWNjb3VudEVtYWlsRG9tYWluIjoiY29ubmVjdC5hdGxhc3NpYW4uY29tIiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL3N5c3RlbUFjY291bnRJZCI6IjcxMjAyMDo4YjY0NzEwOS01YzM1LTRmNDEtYTE2OS00NzcxOTE4ZDEyNTAifQ.vSwgHI8kGbKsI2Thgx0uoba1GflddrzXhuVL1EYZiWUUVHNX1Jeadn6huAZdO4Dpnv2mu4KY8F6KPP53sjKCOTyOd-zbnLjPIAgZPm_AKyanVUBgTC6XJrhsBBlbrvraMBuU9US3pyVmvZVOJWrE6y2xNVunNC_ep-wIcJcVnYuJaX3qjW43RSaebPjsSNB7PtdH6ZSw9qyM50YZqUTVw2l682ft39G993f3kr7MeLcSmipEyhWvWPI3rWXU7fdEtVvRgg9z1qIbZlLVSDg5lEqizLy3JK33Djq2mu6Dj3aY9tjsBITCMCLJ_43pwx9fZdPZMCVqFz56NICYqXaJNQ"
    cloud_id = "ddd063d1-c577-4b9d-8271-d902cc0bd792"
    domain = "stu-team"
    
    try:
        issue = create_issue(access_token, cloud_id, domain, "SCRUM", "Hello", "30", "Task", "Pham Thi Ngoc Mai")
        print(issue)
    except Exception as e:
        print("Lỗi khi lấy issue:", str(e))

if __name__ == "__main__":
    main()