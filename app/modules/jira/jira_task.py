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
        f'duedate = "{today_hn}" '
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
    access_token = """eyJraWQiOiJhdXRoLmF0bGFzc2lhbi5jb20tQUNDRVNTLTk0ZTczYTkwLTUxYWQtNGFjMS1hOWFjLWU4NGUwNDVjNDU3ZCIsImFsZyI6IlJTMjU2In0.eyJqdGkiOiI1Y2E1MDA5Zi01NWJkLTQxMzItOGZmOC1hN2JiNDVhYTFlNzMiLCJzdWIiOiI3MTIwMjA6MDhjN2RhNWMtNzZhMi00M2IxLTk3MGItY2FhYzVkZTJjMmQwIiwibmJmIjoxNzQ4NzEwNDY1LCJpc3MiOiJodHRwczovL2F1dGguYXRsYXNzaWFuLmNvbSIsImlhdCI6MTc0ODcxMDQ2NSwiZXhwIjoxNzQ4NzE0MDY1LCJhdWQiOiJJM2VaZEU2aE9PVHkwUld2OHU1MVVCeDByUTFFNDBJNCIsInNjb3BlIjoibWFuYWdlOmppcmEtcHJvamVjdCBvZmZsaW5lX2FjY2VzcyByZWFkOmFjY291bnQgcmVhZDphbmFseXRpY3MuY29udGVudDpjb25mbHVlbmNlIHJlYWQ6YXBwLWRhdGE6Y29uZmx1ZW5jZSByZWFkOmJsb2dwb3N0OmNvbmZsdWVuY2UgcmVhZDpjb21tZW50OmNvbmZsdWVuY2UgcmVhZDpjb25mbHVlbmNlLWNvbnRlbnQuYWxsIHJlYWQ6Y29uZmx1ZW5jZS1jb250ZW50LnBlcm1pc3Npb24gcmVhZDpjb25mbHVlbmNlLWNvbnRlbnQuc3VtbWFyeSByZWFkOmNvbmZsdWVuY2UtZ3JvdXBzIHJlYWQ6Y29uZmx1ZW5jZS1wcm9wcyByZWFkOmNvbmZsdWVuY2Utc3BhY2Uuc3VtbWFyeSByZWFkOmNvbmZsdWVuY2UtdXNlciByZWFkOmNvbnRlbnQtZGV0YWlsczpjb25mbHVlbmNlIHJlYWQ6Y29udGVudC5tZXRhZGF0YTpjb25mbHVlbmNlIHJlYWQ6Y29udGVudC5wcm9wZXJ0eTpjb25mbHVlbmNlIHJlYWQ6Y29udGVudDpjb25mbHVlbmNlIHJlYWQ6Y3VzdG9tLWNvbnRlbnQ6Y29uZmx1ZW5jZSByZWFkOmRhdGFiYXNlOmNvbmZsdWVuY2UgcmVhZDplbWJlZDpjb25mbHVlbmNlIHJlYWQ6Zm9sZGVyOmNvbmZsdWVuY2UgcmVhZDpqaXJhLXVzZXIgcmVhZDpqaXJhLXdvcmsgcmVhZDptZSByZWFkOnBhZ2U6Y29uZmx1ZW5jZSByZWFkOnNwYWNlLWRldGFpbHM6Y29uZmx1ZW5jZSByZWFkOnNwYWNlLnByb3BlcnR5OmNvbmZsdWVuY2UgcmVhZDpzcGFjZTpjb25mbHVlbmNlIHJlYWQ6dGFzazpjb25mbHVlbmNlIHJlYWQ6dXNlcjpjb25mbHVlbmNlIHJlYWRvbmx5OmNvbnRlbnQuYXR0YWNobWVudDpjb25mbHVlbmNlIHdyaXRlOmppcmEtd29yayIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS9hdGxfdG9rZW5fdHlwZSI6IkFDQ0VTUyIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9zeXN0ZW1BY2NvdW50SWQiOiI3MTIwMjA6MGIwY2E2MjUtMjQ5Ni00M2ZlLWE3MTgtYzczY2Q5ZGRlMTM1IiwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL3Nlc3Npb25faWQiOiIyYTFhZmQ4NC1mYWU0LTRhOWEtODc3Ni03Mjg1ZGU4NmE4MWYiLCJjbGllbnRfaWQiOiJJM2VaZEU2aE9PVHkwUld2OHU1MVVCeDByUTFFNDBJNCIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9maXJzdFBhcnR5IjpmYWxzZSwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL3ZlcmlmaWVkIjp0cnVlLCJ2ZXJpZmllZCI6InRydWUiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vcHJvY2Vzc1JlZ2lvbiI6InVzLXdlc3QtMiIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS91anQiOiI2YjczZDg4OC00NDU1LTQwOWYtYjI4Ni1jNzdjMjZhY2NiNWUiLCJodHRwczovL2F0bGFzc2lhbi5jb20vZW1haWxEb21haW4iOiJnbWFpbC5jb20iLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vcnRpIjoiZjU0NTgxYmItYjliOS00ODcyLWI5NmUtMDE0MWNkZDcwOTk3IiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tLzNsbyI6dHJ1ZSwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL3ZlcmlmaWVkIjp0cnVlLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vcmVmcmVzaF9jaGFpbl9pZCI6IkkzZVpkRTZoT09UeTBSV3Y4dTUxVUJ4MHJRMUU0MEk0LTcxMjAyMDowOGM3ZGE1Yy03NmEyLTQzYjEtOTcwYi1jYWFjNWRlMmMyZDAtNmYzZjc2ZGQtNjU2ZC00MjM2LTkwZjMtZTI3ODA1ODI0YTRlIiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL29hdXRoQ2xpZW50SWQiOiJJM2VaZEU2aE9PVHkwUld2OHU1MVVCeDByUTFFNDBJNCIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9zeXN0ZW1BY2NvdW50RW1haWxEb21haW4iOiJjb25uZWN0LmF0bGFzc2lhbi5jb20iLCJodHRwczovL2F0bGFzc2lhbi5jb20vc3lzdGVtQWNjb3VudEVtYWlsIjoiYmRjMjhhNzAtODNhNS00YmU2LWJmOTMtZjVmMTQ5NzhhNmFkQGNvbm5lY3QuYXRsYXNzaWFuLmNvbSJ9.jSyJPlTSyT3jWSOyzgHaGmvQdDBjsrHqSlbY233SqLPLf3jutK9lVjT7AYMHtLKUA84LkAPVC8J2DtHi7FdBw4Bpr5DSlx25AzbFivP1YfylGj9Le_oNwzEK2f3Vt1rI4ZPOTy_ki6cmDlaHfSYVxiDkCIjlsLyKEGz85_ydlq0V9sM6uO8RAJ1EzTN-zSdCpVDzzTSAluemBNNyd7e1NgITe4QW-rwVR2hl-5AY_tRJVHQYR_QCzYmL0pW0WXXf5XFDYlwQIGrk1WjbBztSVBPErJyDtACivcCNcxYOvf2JP4DrF8FZgejlDfSCi3Nqgny6t-Yu1yxfoQnR2fQniA"""
    cloud_id = "122d270d-f780-4621-b27d-1989a54e38e5"
    domain = "metalwallcrusher"
    
    try:
        issue = get_today_issues(access_token, cloud_id)
        print(issue)
    except Exception as e:
        print("Lỗi khi lấy issue:", str(e))

if __name__ == "__main__":
    main()