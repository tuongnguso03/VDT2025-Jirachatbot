from atlassian import Jira
import requests
from datetime import datetime
import pytz
import unicodedata
import json

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

def get_worklogs(access_token, cloud_id, issue_key):
    jira = get_jira_client(access_token, cloud_id)
    
    raw_worklogs = jira.issue_get_worklog(issue_key)
    
    if isinstance(raw_worklogs, str):
        worklogs_data = json.loads(raw_worklogs)
    else:
        worklogs_data = raw_worklogs
    
    worklogs = worklogs_data.get("worklogs", [])
    
    formatted_worklogs = []
    for w in worklogs:
        formatted_worklogs.append({
            "id": w.get("id"),
            "author": w.get("author", {}).get("displayName"),
            "timeSpent": w.get("timeSpent"),
            "started": w.get("started"),
            "comment": w.get("comment")
        })
        
    return formatted_worklogs

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

def assign_issue(access_token, cloud_id, issue_key, assignee_displayname=None, assignee_email=None):
    jira = get_jira_client(access_token, cloud_id)
    project_key = issue_key.split('-')[0]
    
    assignee_id = None
    if assignee_email or assignee_displayname:
        assignee_id = get_account_id(jira, project_key, assignee_email, assignee_displayname)

    if assignee_id:
        jira.assign_issue(issue_key, assignee_id)
    else:
        pass

    issue = jira.issue(issue_key)

    return {
        "project_key": project_key,
        "issue_id": issue.get("id", None),
        "issue_key": issue.get("key", None),
        "assignee_id": assignee_id,
        "assignee_displayname": assignee_displayname,
        "summary": issue.get("fields", {}).get("summary", None),
        "description": issue.get("fields", {}).get("description", None),
        "issue_type": issue.get("fields", {}).get("issuetype", {}).get("name", None),
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

def get_comments(access_token, cloud_id, issue_key):
    jira = get_jira_client(access_token, cloud_id)
    comments = jira.issue_get_comments(issue_key)

    if isinstance(comments, str):
        comments_data = json.loads(comments)
    else:
        comments_data = comments

    comments = comments_data.get("comments", [])
    
    formatted_comments = []
    for c in comments:
        formatted_comments.append({
            "id": c.get("id"),
            "author": c.get("author", {}).get("displayName"),
            "body": c.get("body"),
            "created": c.get("created"),
            "updated": c.get("updated")
        })

    return formatted_comments


def add_comment(access_token, cloud_id, issue_key, comment):
    jira = get_jira_client(access_token, cloud_id)
    comment_obj = jira.issue_add_comment(issue_key, comment)
    comment_id = comment_obj.get('id') if isinstance(comment_obj, dict) else getattr(comment_obj, 'id', None)
    return {
        "issue_key": issue_key,
        "comment_id": comment_id,
        "comment": comment,
    }

def edit_comment(access_token, cloud_id, issue_key, comment_id, new_comment, visibility=None, notify_users=True):
    jira = get_jira_client(access_token, cloud_id)
    jira.issue_edit_comment(issue_key, comment_id, new_comment, visibility=visibility, notify_users=notify_users)
    return {
        "issue_key": issue_key,
        "comment_id": comment_id,
        "new_comment": new_comment,
    }

def main():
    access_token = "eyJraWQiOiJhdXRoLmF0bGFzc2lhbi5jb20tQUNDRVNTLTk0ZTczYTkwLTUxYWQtNGFjMS1hOWFjLWU4NGUwNDVjNDU3ZCIsImFsZyI6IlJTMjU2In0.eyJqdGkiOiIxMjU3ZmEwZS1hYmFlLTRmNTUtYmY5Ny05MTk3NjU5YzlhMDUiLCJzdWIiOiI3MTIwMjA6YjZkMTIyYzgtNWY2OC00N2EzLTkwMjUtMTQ4NDc5MTBkNTE4IiwibmJmIjoxNzQ4NTM0NzYwLCJpc3MiOiJodHRwczovL2F1dGguYXRsYXNzaWFuLmNvbSIsImlhdCI6MTc0ODUzNDc2MCwiZXhwIjoxNzQ4NTM4MzYwLCJhdWQiOiJ0VWc5VGpqYTRTSmEwTld5M0tBUGNjQXI0M3BiZGNIdSIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS9yZWZyZXNoX2NoYWluX2lkIjoidFVnOVRqamE0U0phME5XeTNLQVBjY0FyNDNwYmRjSHUtNzEyMDIwOmI2ZDEyMmM4LTVmNjgtNDdhMy05MDI1LTE0ODQ3OTEwZDUxOC03NDJjNzQzMC1lYjg0LTQxZDItYjE5Mi1jZDg1MzVhZjBhZDIiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vdWp0IjoiMDc4ZDk1NzYtNTIxOC00YzZiLWJlYWItNWY1MTRkMTc4YTE5IiwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL2F0bF90b2tlbl90eXBlIjoiQUNDRVNTIiwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL3Nlc3Npb25faWQiOiI2ZjQ0MjQ5YS04NzNhLTRmZTgtOWMyNS1hMzA3MWNhMGEzZjQiLCJodHRwczovL2F0bGFzc2lhbi5jb20vZmlyc3RQYXJ0eSI6ZmFsc2UsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS92ZXJpZmllZCI6dHJ1ZSwiY2xpZW50X2lkIjoidFVnOVRqamE0U0phME5XeTNLQVBjY0FyNDNwYmRjSHUiLCJzY29wZSI6Im1hbmFnZTpqaXJhLXByb2plY3Qgb2ZmbGluZV9hY2Nlc3MgcmVhZDphY2NvdW50IHJlYWQ6amlyYS11c2VyIHJlYWQ6amlyYS13b3JrIHJlYWQ6bWUgd3JpdGU6amlyYS13b3JrIiwidmVyaWZpZWQiOiJ0cnVlIiwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL3Byb2Nlc3NSZWdpb24iOiJ1cy13ZXN0LTIiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vcnRpIjoiNGEwOTg0YjktMGExMC00YzM0LTg1NTQtNmRjNzgyZjM0NjE1IiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL2VtYWlsRG9tYWluIjoiZ21haWwuY29tIiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL3N5c3RlbUFjY291bnRFbWFpbCI6Ijc2MzNlMzQyLWM0YzctNGFmMS04NDU0LTMzMjMwYTE1ZTM0NUBjb25uZWN0LmF0bGFzc2lhbi5jb20iLCJodHRwczovL2F0bGFzc2lhbi5jb20vM2xvIjp0cnVlLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vdmVyaWZpZWQiOnRydWUsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9vYXV0aENsaWVudElkIjoidFVnOVRqamE0U0phME5XeTNLQVBjY0FyNDNwYmRjSHUiLCJodHRwczovL2F0bGFzc2lhbi5jb20vc3lzdGVtQWNjb3VudEVtYWlsRG9tYWluIjoiY29ubmVjdC5hdGxhc3NpYW4uY29tIiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL3N5c3RlbUFjY291bnRJZCI6IjcxMjAyMDo4YjY0NzEwOS01YzM1LTRmNDEtYTE2OS00NzcxOTE4ZDEyNTAifQ.MIgNlPvxOhCxyB8qX9DC3wItm8eBYr_Pnj1smfJrrRUfKB4w74djcPeCjcAz9IOCdfa8SGJUQGqlzw3lFAh7rovZe7cWsQQCwvmaGV6tuMizO_CQAURCpImY7PJeli-s75-Z4Y4qP75z3bLPBeyMnzRC3dsMY4V-iVLEFZ1LhWHdG_HC54Mdi0LGQao0_vFHBPkcrCvfb5RXjzg6pgySPM-qz3NEu6WP0Xyk4qoydm0VOYy6YlfixsON9fqtiWdDNuNGuxDzUSDAE5lzEwwNZwqhOH4BX8d82810SMmW_MF963-5NrklUWgk5ufukBwE7j3jnNGC7WZMRtQnvUWW9g"
    cloud_id = "ddd063d1-c577-4b9d-8271-d902cc0bd792"
    domain = "stu-team"
    
    try:
        issue = get_worklogs(access_token, cloud_id, "SCRUM-6")
        print(issue)
    except Exception as e:
        print("Lỗi khi lấy issue:", str(e))

if __name__ == "__main__":
    main()