from atlassian import Jira
import requests
from datetime import datetime
import pytz

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

def log_work(access_token, cloud_id, issue_key, time_spent, comment=""):
    jira = get_jira_client(access_token, cloud_id)
    url = f"/rest/api/3/issue/{issue_key}/worklog"
    payload = {
        "timeSpent": time_spent,
        "comment": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": comment
                        }
                    ]
                }
            ]
        }
    }

    response = jira.post(url, data=payload)

    return {
        "worklog_id": response.get("id"),
        "issue_key": issue_key,
        "time_spent": time_spent,
        "comment": comment,
        "author": response.get("author", {}).get("displayName") if response.get("author") else None,
        "created": response.get("created"),
        "updated": response.get("updated")
    }

def get_account_id(email, access_token, cloud_id):
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}.atlassian.net/rest/api/3/user/search?query={email}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    response = requests.get(url, headers=headers)
    users = response.json()
    if users:
        return users[0].get("accountId")
    return None

def create_issue(access_token, cloud_id, project_key, summary, description, issue_type="Task", assignee_email=None):
    jira = get_jira_client(access_token, cloud_id)
    
    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "description": description,
        "issuetype": {"name": issue_type}
    }
    
    assignee_id = None
    if assignee_email:
        assignee_id = get_account_id(assignee_email, access_token, cloud_id)

    if assignee_id:
        fields["assignee"] = {"accountId": assignee_id}
    
    issue = jira.create_issue(fields=fields)
    
    return {
        "issue_id": getattr(issue, "id", None),
        "issue_key": getattr(issue, "key", None),
        "issue_url": f"https://{cloud_id}.atlassian.net/browse/{getattr(issue, 'key', '')}",
        "summary": summary,
        "assignee_id": assignee_id,
        "issue_type": issue_type,
        "description": description,
        "status": getattr(issue.fields, "status", {}).name if hasattr(issue, "fields") and hasattr(issue.fields, "status") else None,
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
    access_token = "eyJraWQiOiJhdXRoLmF0bGFzc2lhbi5jb20tQUNDRVNTLTk0ZTczYTkwLTUxYWQtNGFjMS1hOWFjLWU4NGUwNDVjNDU3ZCIsImFsZyI6IlJTMjU2In0.eyJqdGkiOiJhZGFkNjU2YS04YTVkLTRkODQtOTFmOS0zMjExMDViNDU5NDUiLCJzdWIiOiI3MTIwMjA6YjZkMTIyYzgtNWY2OC00N2EzLTkwMjUtMTQ4NDc5MTBkNTE4IiwibmJmIjoxNzQ4NDMwNDQ5LCJpc3MiOiJodHRwczovL2F1dGguYXRsYXNzaWFuLmNvbSIsImlhdCI6MTc0ODQzMDQ0OSwiZXhwIjoxNzQ4NDM0MDQ5LCJhdWQiOiJ0VWc5VGpqYTRTSmEwTld5M0tBUGNjQXI0M3BiZGNIdSIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS9yZWZyZXNoX2NoYWluX2lkIjoidFVnOVRqamE0U0phME5XeTNLQVBjY0FyNDNwYmRjSHUtNzEyMDIwOmI2ZDEyMmM4LTVmNjgtNDdhMy05MDI1LTE0ODQ3OTEwZDUxOC1kNGM1NWQ5Ni1kOGY1LTQ4ZGItOGQzYy03Mjg1M2JjYmVhY2QiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vYXRsX3Rva2VuX3R5cGUiOiJBQ0NFU1MiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vc2Vzc2lvbl9pZCI6IjZmNDQyNDlhLTg3M2EtNGZlOC05YzI1LWEzMDcxY2EwYTNmNCIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9maXJzdFBhcnR5IjpmYWxzZSwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL3ZlcmlmaWVkIjp0cnVlLCJjbGllbnRfaWQiOiJ0VWc5VGpqYTRTSmEwTld5M0tBUGNjQXI0M3BiZGNIdSIsInNjb3BlIjoibWFuYWdlOmppcmEtcHJvamVjdCBvZmZsaW5lX2FjY2VzcyByZWFkOmFjY291bnQgcmVhZDpqaXJhLXVzZXIgcmVhZDpqaXJhLXdvcmsgcmVhZDptZSB3cml0ZTpqaXJhLXdvcmsiLCJ2ZXJpZmllZCI6InRydWUiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vcHJvY2Vzc1JlZ2lvbiI6InVzLXdlc3QtMiIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9lbWFpbERvbWFpbiI6ImdtYWlsLmNvbSIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9zeXN0ZW1BY2NvdW50RW1haWwiOiI3NjMzZTM0Mi1jNGM3LTRhZjEtODQ1NC0zMzIzMGExNWUzNDVAY29ubmVjdC5hdGxhc3NpYW4uY29tIiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tLzNsbyI6dHJ1ZSwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL3J0aSI6IjhiZDNmNGUyLTg4MDEtNDQ2Yy1iMTcwLTBkODRmMDNiN2UxNSIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS91anQiOiJjMDBhZDBlMy0yYTQ0LTQxNDItYjhkMy1mZmFkMTdiMTc0NjUiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vdmVyaWZpZWQiOnRydWUsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9vYXV0aENsaWVudElkIjoidFVnOVRqamE0U0phME5XeTNLQVBjY0FyNDNwYmRjSHUiLCJodHRwczovL2F0bGFzc2lhbi5jb20vc3lzdGVtQWNjb3VudEVtYWlsRG9tYWluIjoiY29ubmVjdC5hdGxhc3NpYW4uY29tIiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL3N5c3RlbUFjY291bnRJZCI6IjcxMjAyMDo4YjY0NzEwOS01YzM1LTRmNDEtYTE2OS00NzcxOTE4ZDEyNTAifQ.a9_CqLu0iVxs_yGiIc5Qxn1s0-QuJb43JA13AfzSmYgk6miW9kae2TntwfudpvI4sO2rJ7NVZWy-OnSnjjZeSlaL0-ISaO96MtonA29rcpz_pvnb8BS__wnL1eDi2e676DUjVKC4RjYonO-w7_e5nMapTXVjTttjlbNIczXdIk9zuWGQIf-xdxUa7mtNWJ8AJEI5wBi8EqnPSl1JRqWOIlBoBnqgy22nemB2DwM3wxvWF4i4R0xtiyF8glhl32CyX9_eZTc_EWKMdJBxLxf2GGPjz5pgyFT6sViEzK2qLzyt2EnZAV_mTw4DVHBfE4N95WjDDwehN26nry_F2F4NGw"
    cloud_id = "ddd063d1-c577-4b9d-8271-d902cc0bd792"
    
    try:
        issue = transition_issue(access_token, cloud_id, "SCRUM-177", "Done")
        print(issue)
    except Exception as e:
        print("Lỗi khi lấy issue:", str(e))

if __name__ == "__main__":
    main()