from atlassian import Jira
import requests
from datetime import datetime
import pytz
import unicodedata
import json
import re
import os

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
            "type": fields["issuetype"].get("name"),
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
            "type": issue["fields"]["issuetype"].get("name"),
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
        "type": fields["issuetype"].get("name"),
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
            "issue_key": issue_key,
            "id": w.get("id"),
            "author": w.get("author", {}).get("displayName"),
            "time_spent": w.get("timeSpent"),
            "started": w.get("started"),
            "comment": w.get("comment")
        })
        
    return formatted_worklogs


def format_started(user_input: str = None, tz='Asia/Ho_Chi_Minh'):
    timezone = pytz.timezone(tz)
    now = datetime.now(timezone)

    if not user_input or user_input.strip() == "":
        dt = now 
    elif re.match(r"^\d{2}:\d{2}$", user_input):
        dt = datetime.strptime(now.strftime("%Y-%m-%d") + " " + user_input, "%Y-%m-%d %H:%M")
        dt = timezone.localize(dt)
    elif re.match(r"^\d{4}-\d{2}-\d{2}$", user_input):
        dt = datetime.strptime(user_input + " " + now.strftime("%H:%M"), "%Y-%m-%d %H:%M")
        dt = timezone.localize(dt)
    else:
        dt = datetime.strptime(user_input, "%Y-%m-%d %H:%M")
        dt = timezone.localize(dt)

    return dt.strftime('%Y-%m-%dT%H:%M:%S.000%z')

def log_work(access_token, cloud_id, issue_key, time_spend, comment, date=None):
    jira = get_jira_client(access_token, cloud_id)
    started = format_started(date)
    
    worklog = jira.issue_worklog(issue_key, started, time_spend*60, comment)

    log_id = worklog.get('id')
    author_name = worklog.get('author', {}).get('displayName', 'Unknown')

    return {
        "issue_key": issue_key,
        "started": started,
        "time_spend": time_spend,
        "comment": comment,
        "id": log_id,
        "author": author_name
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

def get_account_id(jira, project_key, assignee_displayname=None):
    users = jira.get_all_assignable_users_for_project(project_key, start=0, limit=100)

    for user in users:
        display_name = user.get("displayName", "")
        email = user.get("emailAddress", "")
        account_id = user.get("accountId")

        if assignee_displayname and normalize(display_name) == normalize(assignee_displayname):
            return account_id

    return None

def create_issue(access_token, cloud_id, domain, project_key, summary, description, issue_type, due_date=None, assignee_displayname=None):
    jira = get_jira_client(access_token, cloud_id)
    
    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "description": description,
        "issuetype": {"name": issue_type}
    }

    if due_date:
        try:
            parsed_date = datetime.strptime(due_date, "%d/%m/%Y")
            fields["duedate"] = parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Định dạng ngày không hợp lệ: {due_date}. Vui lòng dùng định dạng dd/MM/YYYY.")
    
    assignee_id = None
    if assignee_displayname:
        assignee_id = get_account_id(jira, project_key, assignee_displayname)

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
        "due_date": due_date
    }

def assign_issue(access_token, cloud_id, issue_key, assignee_displayname=None):
    jira = get_jira_client(access_token, cloud_id)
    project_key = issue_key.split('-')[0]
    
    assignee_id = None
    if assignee_displayname:
        assignee_id = get_account_id(jira, project_key, assignee_displayname)

    if assignee_id:
        jira.assign_issue(issue_key, assignee_id)
    else:
        pass

    issue = jira.issue(issue_key)
    fields = issue.get("fields", {})

    due_date_raw = fields.get("duedate")
    due_date_formatted = None
    if due_date_raw:
        try:
            due_date_formatted = datetime.strptime(due_date_raw, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            due_date_formatted = due_date_raw

    return {
        "project_key": project_key,
        "issue_key": issue.get("key", None),
        "assignee_id": assignee_id,
        "assignee_displayname": assignee_displayname,
        "summary": fields.get("summary", None),
        "description": fields.get("description", None),
        "issue_type": fields.get("issuetype", {}).get("name", None),
        "due_date": due_date_formatted,
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


def add_attachment(access_token, cloud_id, issue_key, file_path):
    jira = get_jira_client(access_token, cloud_id)

    try:
        with open(file_path, "rb") as f:
            jira.add_attachment_object(issue_key, f)

        return f" Đã đính kèm file vào issue `{issue_key}` thành công."

    except Exception as e:
        return f"❌ Lỗi khi upload file vào `{issue_key}`: {str(e)}"
    

def main():
    access_token = "eyJraWQiOiJhdXRoLmF0bGFzc2lhbi5jb20tQUNDRVNTLTk0ZTczYTkwLTUxYWQtNGFjMS1hOWFjLWU4NGUwNDVjNDU3ZCIsImFsZyI6IlJTMjU2In0.eyJqdGkiOiJhYzYzMWY1MS1iZDQwLTRhYTYtYTgxOS1kYWEyZjZkOTUzMGYiLCJzdWIiOiI3MTIwMjA6YjZkMTIyYzgtNWY2OC00N2EzLTkwMjUtMTQ4NDc5MTBkNTE4IiwibmJmIjoxNzQ4NzA1MDg0LCJpc3MiOiJodHRwczovL2F1dGguYXRsYXNzaWFuLmNvbSIsImlhdCI6MTc0ODcwNTA4NCwiZXhwIjoxNzQ4NzA4Njg0LCJhdWQiOiJJM2VaZEU2aE9PVHkwUld2OHU1MVVCeDByUTFFNDBJNCIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS9ydGkiOiI4OTNkNTllNS1mMzdlLTQzZTctYmVlYy1mNDAwOWRmNzlhMzgiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vcmVmcmVzaF9jaGFpbl9pZCI6IkkzZVpkRTZoT09UeTBSV3Y4dTUxVUJ4MHJRMUU0MEk0LTcxMjAyMDpiNmQxMjJjOC01ZjY4LTQ3YTMtOTAyNS0xNDg0NzkxMGQ1MTgtZGVhZGRkMTktYjM3Yi00MmU0LTk4YjQtMjNlNzY2MzA4MTRjIiwic2NvcGUiOiJtYW5hZ2U6amlyYS1wcm9qZWN0IG9mZmxpbmVfYWNjZXNzIHJlYWQ6YWNjb3VudCByZWFkOmFuYWx5dGljcy5jb250ZW50OmNvbmZsdWVuY2UgcmVhZDphcHAtZGF0YTpjb25mbHVlbmNlIHJlYWQ6YmxvZ3Bvc3Q6Y29uZmx1ZW5jZSByZWFkOmNvbW1lbnQ6Y29uZmx1ZW5jZSByZWFkOmNvbmZsdWVuY2UtY29udGVudC5hbGwgcmVhZDpjb25mbHVlbmNlLWNvbnRlbnQucGVybWlzc2lvbiByZWFkOmNvbmZsdWVuY2UtY29udGVudC5zdW1tYXJ5IHJlYWQ6Y29uZmx1ZW5jZS1ncm91cHMgcmVhZDpjb25mbHVlbmNlLXByb3BzIHJlYWQ6Y29uZmx1ZW5jZS1zcGFjZS5zdW1tYXJ5IHJlYWQ6Y29uZmx1ZW5jZS11c2VyIHJlYWQ6Y29udGVudC1kZXRhaWxzOmNvbmZsdWVuY2UgcmVhZDpjb250ZW50Lm1ldGFkYXRhOmNvbmZsdWVuY2UgcmVhZDpjb250ZW50LnByb3BlcnR5OmNvbmZsdWVuY2UgcmVhZDpjb250ZW50OmNvbmZsdWVuY2UgcmVhZDpjdXN0b20tY29udGVudDpjb25mbHVlbmNlIHJlYWQ6ZGF0YWJhc2U6Y29uZmx1ZW5jZSByZWFkOmVtYmVkOmNvbmZsdWVuY2UgcmVhZDpmb2xkZXI6Y29uZmx1ZW5jZSByZWFkOmppcmEtdXNlciByZWFkOmppcmEtd29yayByZWFkOm1lIHJlYWQ6cGFnZTpjb25mbHVlbmNlIHJlYWQ6c3BhY2UtZGV0YWlsczpjb25mbHVlbmNlIHJlYWQ6c3BhY2UucHJvcGVydHk6Y29uZmx1ZW5jZSByZWFkOnNwYWNlOmNvbmZsdWVuY2UgcmVhZDp0YXNrOmNvbmZsdWVuY2UgcmVhZDp1c2VyOmNvbmZsdWVuY2UgcmVhZG9ubHk6Y29udGVudC5hdHRhY2htZW50OmNvbmZsdWVuY2Ugd3JpdGU6amlyYS13b3JrIiwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL2F0bF90b2tlbl90eXBlIjoiQUNDRVNTIiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL3N5c3RlbUFjY291bnRJZCI6IjcxMjAyMDowYjBjYTYyNS0yNDk2LTQzZmUtYTcxOC1jNzNjZDlkZGUxMzUiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vc2Vzc2lvbl9pZCI6IjZmNDQyNDlhLTg3M2EtNGZlOC05YzI1LWEzMDcxY2EwYTNmNCIsImNsaWVudF9pZCI6IkkzZVpkRTZoT09UeTBSV3Y4dTUxVUJ4MHJRMUU0MEk0IiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL2ZpcnN0UGFydHkiOmZhbHNlLCJodHRwczovL2F0bGFzc2lhbi5jb20vdmVyaWZpZWQiOnRydWUsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS91anQiOiI2N2QyOWEyNS0yNGFjLTRkZTgtYmRkZS0wNTBmYzk5MjRhMDIiLCJ2ZXJpZmllZCI6InRydWUiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vcHJvY2Vzc1JlZ2lvbiI6InVzLXdlc3QtMiIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9lbWFpbERvbWFpbiI6ImdtYWlsLmNvbSIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS8zbG8iOnRydWUsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS92ZXJpZmllZCI6dHJ1ZSwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL29hdXRoQ2xpZW50SWQiOiJJM2VaZEU2aE9PVHkwUld2OHU1MVVCeDByUTFFNDBJNCIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9zeXN0ZW1BY2NvdW50RW1haWxEb21haW4iOiJjb25uZWN0LmF0bGFzc2lhbi5jb20iLCJodHRwczovL2F0bGFzc2lhbi5jb20vc3lzdGVtQWNjb3VudEVtYWlsIjoiYmRjMjhhNzAtODNhNS00YmU2LWJmOTMtZjVmMTQ5NzhhNmFkQGNvbm5lY3QuYXRsYXNzaWFuLmNvbSJ9.wdOg4v8h3GVTWmY1LjGMeZBJmeHTuIrJwVdbcpVWjXjGQcidF--lemlsncu25xsTDWP6wjGbDsdtgFzWztGOUW5TNAxXlyxcDy87blfmVvyg02Bw5-hY2nq-TzuXRgY8hwHbN6jaBzELT2HfV1gea1ztx7e3jADlm-G_VDsD7SQQBzyPuSXAKjWPKAssoxKEKAK_air2Cnnd5SqJClt9o5nFuz2oAx-pwspTHHshIHcRPSn8CJ2AVafPWFLQ8sjzm3_nZAP4yxBNRR_GwTf48RIV58w9TG33M9Bz0X8pnHtXYyfsaHdWVXffSotY6K6UgPlpcxYl0jwMfFmjapZcEg"
    cloud_id = "122d270d-f780-4621-b27d-1989a54e38e5"
    domain = "metalwallcrusher"
    
    try:
        issue = get_comments(access_token, cloud_id, "VDT-1")
        print(issue)
    except Exception as e:
        print("Lỗi khi lấy issue:", str(e))

if __name__ == "__main__":
    main()