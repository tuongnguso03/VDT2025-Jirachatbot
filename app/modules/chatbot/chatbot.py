from google import genai
from google.genai import types as genai_types
from .utils.function_declaration import GeminiFunction
import os
from dotenv import load_dotenv
from typing import List, Dict
import json
import re
from modules.vector_db.vector_db import VectorDatabase
from datetime import datetime
from modules.confluence.confluence_doc import get_page_by_id_v2, get_all_page_ids_and_titles_v2
from modules.jira.jira_task import get_all_issues, get_today_issues, get_issue_detail, get_worklogs, log_work, create_issue, assign_issue, transition_issue, get_comments, add_comment, edit_comment, add_attachment

load_dotenv()

class ChatAgent:
    """
    The chat agent class. Handle everything chat. Or that sort.
    """
    client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    model = "gemini-2.5-flash-preview-05-20"
    config = {"temperature": 0, "maxOutputTokens": 1024}
    
    def __init__(self, user_id: str, access_token: str, cloud_id: str, domain: str, user_projects: str = "TS"):
        self.user_id = user_id
        self.access_token = access_token
        self.cloud_id = cloud_id
        self.domain = domain
        self.user_projects = user_projects
        self.functions = [
            self.get_jira_issues, 
            self.get_jira_issues_today,
            self.get_jira_issue_detail,
            self.get_jira_log_works,
            self.create_jira_log_work,
            self.create_jira_issue,
            self.assign_jira_issue,
            self.transition_jira_issue,
            self.get_jira_comments,
            self.create_jira_comment,
            self.edit_jira_comment,
            self.get_confluence_page_info,
            self.get_confluence_page_list,
            self.get_task_related_info_from_query]
        self.system_message = """
        Bạn là VDT-2025-Tele-Bot, một Chatbot hỗ trợ công việc trên Jira và Confluence thông qua Telegram.
        Bạn có khả năng truy cập vào các hàm và gọi các hàm đó phục vụ cho yêu cầu của người dùng.
        ### BẠN CÓ KHẢ NĂNG HIỂU Ý CỦA NGƯỜI DÙNG DỰA TRÊN CUỘC TRÒ CHUYỆN. ĐỪNG HỎI LẠI KHI KHÔNG CẦN THIẾT.

        ## CHÚ Ý:
            - Nếu bạn có một hàm nào có thể hỗ trợ người dùng, hãy sử dụng. Sau khi nhận được kết quả, hãy trả lời người dùng đúng theo yêu cầu.
            ### LUÔN LUÔN CỐ GẮNG THỬ SỬ DỤNG CÁC HÀM, DÙ KẾT QUẢ TRẢ VỀ CÓ THỂ KHÔNG ĐÚNG
            - Nếu bạn không có một hàm nào có thể hỗ trợ, hãy trả lời đúng theo khả năng của mình.
        """


    def get_jira_issues(self):
        """
        Lấy ra danh sách tasks (công việc) của người dùng và định dạng thành bảng MarkdownV2 hoặc plaint text.

        Trả về:
            Chuỗi MarkdownV2 hoặc plaint text để gửi qua Telegram. Không được viết thêm gì nữa.
        """
        result = get_all_issues(self.access_token, self.cloud_id)

        if not result:
            return "🎉 Bạn không có công việc nào đang xử lý!"

        def escape_markdown(text: str) -> str:
            chars_to_escape = r"\_*[]()~`>#+-=|{}.!-"
            for ch in chars_to_escape:
                text = text.replace(ch, f"\\{ch}")
            return text

        def format_markdown_table(issues: list[dict]) -> str:
            MAX_SUMMARY_LENGTH = 21
            MAX_KEY_LENGTH = 8

            col_widths = {
                "key": MAX_KEY_LENGTH,
                "summary": MAX_SUMMARY_LENGTH,
                "priority": max(len("Priority"), max((len(issue.get("priority") or "") for issue in issues), default=0)),
                "deadline": max(len("Deadline"), max((len(issue.get("deadline")) if issue["deadline"] else 0 for issue in issues), default=0)),
            }

            def pad(text: str, width: int) -> str:
                return text.ljust(width)

            lines = []

            lines.append(
                f"{pad('Key', (col_widths['key'])-2)} | "
                f"{pad('Summary', col_widths['summary'])} | "
                f"{pad('Priority', col_widths['priority'])} | "
                f"{pad('Deadline', col_widths['deadline'])}"
            )

            lines.append(
                f"{'-' * (col_widths['key'] - 2)} | "
                f"{'-' * col_widths['summary']} | "
                f"{'-' * col_widths['priority']} | "
                f"{'-' * col_widths['deadline']}"
            )

            for issue in issues:
                key_raw = issue.get("key") or ""
                key = pad(escape_markdown(key_raw), col_widths['key'])

                summary_raw = issue.get("summary") or ""
                summary_cut = summary_raw[:MAX_SUMMARY_LENGTH]
                if len(summary_raw) > MAX_SUMMARY_LENGTH:
                    summary_cut = summary_cut[:-3] + "..."
                summary = pad(escape_markdown(summary_cut), col_widths['summary'])

                priority_raw = issue.get("priority") or ""
                priority = pad(escape_markdown(priority_raw), col_widths['priority'])

                deadline = issue['deadline'] if issue['deadline'] else ""
                deadline = pad(escape_markdown(deadline), col_widths['deadline'])

                lines.append(f"{key} | {summary} | {priority} | {deadline}")

            table = "\n".join(lines)
            return f"Đây là danh sách công việc của bạn:```\n{table}\n```"

        return format_markdown_table(result)


    def get_jira_issues_today(self):
        """
        Lấy ra danh sách tasks (công việc) của người dùng ngày hôm nay và định dạng thành bảng MarkdownV2 hoặc plaint text.

        Trả về:
            Hàm này trả về khối mã được định dạng theo MarkdownV2 hoặc plaint text. Không thêm bất kỳ văn bản nào. Không thêm bất kỳ mô tả hoặc tóm tắt nào
        """
        result = get_today_issues(self.access_token, self.cloud_id)

        if not result:
            return "🎉 Bạn không có công việc nào đang xử lý!"

        def escape_markdown(text: str) -> str:
            chars_to_escape = r"\_*[]()~`>#+-=|{}.-!"
            for ch in chars_to_escape:
                text = text.replace(ch, f"\\{ch}")
            return text

        def format_markdown_table(issues: list[dict]) -> str:
            MAX_SUMMARY_LENGTH = 22
            MAX_KEY_LENGTH = 8

            headers = ["Key", "Summary", "Type", "Priority", "Deadline"]
            col_widths = {
                "key": MAX_KEY_LENGTH,
                "summary": MAX_SUMMARY_LENGTH,
                "type": max(len("Type"), max((len(issue["type"]) for issue in issues), default=0)),
                "priority": max(len("Priority"), max((len(issue.get("priority") or "") for issue in issues), default=0)),
            }

            def pad(text: str, width: int) -> str:
                return text.ljust(width)

            lines = []

            lines.append(
                f"{pad('Key', (col_widths['key'])-2)} | "
                f"{pad('Summary', col_widths['summary'])} | "
                f"{pad('Type', col_widths['type'])} | "
                f"{pad('Priority', col_widths['priority'])}"
            )

            lines.append(
                f"{'-' * (col_widths['key'] - 2)} | "
                f"{'-' * col_widths['summary']} | "
                f"{'-' * col_widths['type']} | "
                f"{'-' * col_widths['priority']}"
            )

            for issue in issues:
                key_raw = issue.get("key") or ""
                key = pad(escape_markdown(key_raw), col_widths['key'])

                summary_raw = issue.get("summary") or ""
                summary_cut = summary_raw[:MAX_SUMMARY_LENGTH]
                if len(summary_raw) > MAX_SUMMARY_LENGTH:
                    summary_cut = summary_cut[:-3] + "..."
                summary = pad(escape_markdown(summary_cut), col_widths['summary'])

                type_raw = issue.get("type") or ""
                type = pad(escape_markdown(type_raw), col_widths['type'])

                priority_raw = issue.get("priority") or ""
                priority = pad(escape_markdown(priority_raw), col_widths['priority'])

                lines.append(f"{key} | {summary} | {type} | {priority}")

            table = "\n".join(lines)
            return f"Đây là danh sách công việc của bạn hôm nay:```\n{table}\n```"

        return format_markdown_table(result)
    
    
    def get_jira_issue_detail(self, issue_key: str):
        """
        Lấy ra chi tiết của một task từ issue_key
        
        Hàm này nhận vào key của một issue trong Jira và trả về thông tin chi tiết của issue đó.

        Tham số:
            issue_key (str): key của issue cần lấy thông tin. Có thể bao gồm cả chữ và số.
            
        Trả về:
            Thông tin dự án đúng như hàm function call đã response.
        """
        result = get_issue_detail(self.access_token, self.cloud_id, issue_key)

        attachment_urls = [att.get("content_url") for att in result.get("attachments", []) if att.get("content_url")]
        
        formatted = f"Thông tin chi tiết task {issue_key}:\n\n"
        formatted += (
            f"  📂  Dự án: {result.get('project', '')}\n"
            f"  🔑  Jira Issue: {result.get('key', '')}\n"
            f"  📝  Tóm tắt: {result.get('summary', '')}\n"
            f"  ✏️  Mô tả: {result.get('description', '')}\n"
            f"  🔖  Loại: {result.get('type', '')}\n"
            f"  ⭐  Mức độ ưu tiên: {result.get('priority', '')}\n"
            f"  📅  Deadline: {result.get('duedate', 'Không có')}\n"
            f"  🚦  Trạng thái: {result.get('status', '')}\n"
            f"  👷‍♂️  Người thực hiện: {result.get('assignee', 'Không có')}\n"
            f"  🧾  Người tạo: {result.get('reporter', '')}\n"
        )

        if attachment_urls:
            formatted += f"  - Attachments: {json.dumps(attachment_urls)}\n"

        return formatted
            
    
    def get_jira_log_works(self, issue_key: str):
        """
        Lấy ra danh sách worklog của một task từ issue_key.

        Hàm này nhận vào key của một issue trong Jira và trả về danh sách worklog cho issue đó.

        Tham số:
            issue_key (str): key của issue cần lấy thông tin. Có thể bao gồm cả chữ và số.

        Trả về:
            Chuỗi MarkdownV2 hoặc plaint text để gửi qua Telegram. Trả về y hệt như đã format không được thêm thắt gì nữa.
        """
        result = get_worklogs(self.access_token, self.cloud_id, issue_key)

        if not result:
            return "Issue này chưa có worklog!"

        def escape_markdown(text: str) -> str:
            chars_to_escape = r"\_*[]()~`>#+-=|{}.!-"
            for ch in chars_to_escape:
                text = text.replace(ch, f"\\{ch}")
            return text
        
        MAX_COMMENT_LENGTH = 30

        def format_markdown_table(issues: list[dict]) -> str:
            headers = ["ID", "Author", "Start", "Time", "Comment"]
            col_widths = {
                "id": max(len("ID"), max((len(issue["id"]) for issue in issues), default=0)),
                "author": max(len("Author"), max((len(issue["author"]) for issue in issues), default=0)),
                "started": max(len("Start"), max((len(issue["started"]) for issue in issues), default=0)),
                "time_spent": max(len("Time"), max((len(issue.get("time_spent") or "") for issue in issues), default=0)),
                "comment": max(len("Comment"), max((len(issue["comment"]) if issue["comment"] else 0 for issue in issues), default=0)),
            }

            def pad(text: str, width: int) -> str:
                return text + ' ' * (width - len(text))

            lines = []

            lines.append(
                # f"{pad('ID', col_widths['id'])} | "
                f"{pad('Author', col_widths['author'])} | "
                # f"{pad('Started', col_widths['started'])} | "
                f"{pad('Time', col_widths['time_spent'])} | "
                f"{pad('Comment', col_widths['comment'])}"
            )

            lines.append(
                # f"{'-' * (col_widths['id'] + 1)}|"
                f"{'-' * (col_widths['author'] + 1)}|"
                # f"{'-' * (col_widths['started'] + 2)}|"
                f"{'-' * (col_widths['time_spent'] + 2)}|"
                f"{'-' * (col_widths['comment'] + 1)}"
            )

            for issue in issues:
                # id = pad(escape_markdown(issue['id']), col_widths['id'])
                author = pad(escape_markdown(issue['author']), col_widths['author'])
                # started = pad(escape_markdown(issue['started']), col_widths['started'])
                time_spent = pad(escape_markdown(issue['time_spent']), col_widths['time_spent'])
                comment_raw = issue.get("comment") or ""
                comment_cut = comment_raw[:MAX_COMMENT_LENGTH]
                if len(comment_raw) > MAX_COMMENT_LENGTH:
                    comment_cut = comment_cut[:-3] + "..."
                comment = pad(escape_markdown(comment_cut), col_widths['comment'])

                lines.append(
                    f"{author} | {time_spent} | {comment}"
                )
        
            table = "\n".join(lines)
            return f"Đây là danh sách worklog:```\n{table}\n```"

        return format_markdown_table(result)

    def create_jira_log_work(self, issue_key: str, time_spend: int, comment: str, date: str):
        """
        Log work cho một task từ issue_key, time_spend, comment, date

        Hàm này nhận vào key của một issue trong Jira, ngày, thời gian làm việc và bình luận, và trả về thông tin chi tiết của log work cho issue đó.

        Tham số:
            issue_key (str): key của issue cần lấy thông tin. Có thể bao gồm cả chữ và số.
            date (str): Ngày log work, định dạng linh hoạt (YYYY-MM-DD HH:MM, hoặc chỉ HH:MM hoặc rỗng).
            time_spend (int): Thời gian làm việc - làm trong bao nhiêu phút.
            comment (str): Bình luận cho log work.

        Trả về:
            Thông tin worklog đầy đủ sau đã formatted gồm cả icon.
        """
        result = log_work(self.access_token, self.cloud_id, issue_key, time_spend, comment, date)

        started_raw = result.get("started", "")
        started_str = ""
        if started_raw:
            dt = datetime.strptime(started_raw, "%Y-%m-%dT%H:%M:%S.000%z")
            started_str = dt.strftime("%H:%M %d-%m-%Y")

        formatted = (
            f"- Jira Issue: {result.get('issue_key', '')}\n"
            f"- Người log work: {result.get('author', '')}\n"
            f"- Thời gian làm việc: {result.get('time_spend', '')} phút\n"
            f"- Thời gian bắt đầu làm: {started_str}\n"
            f"- Comment: {result.get('comment', 'Không có')}\n"
        )

        return f"✅ Đã log work thành công!\n{formatted}"
    
    def create_jira_issue(self, project_key: str, summary: str, description: str, issue_type: str, due_date: str, assignee_displayname: str, priority: str):
        """
        Tạo mới (task) issue từ project_key, summary, description, issue_type, assignee_displayname, due_date, priority

        Hàm này nhận vào key của một project trong Jira, ngày, tóm tắt, mô tả, loại issue, ngày đến hạn, assignee_displayname của người được giao task và priority của task.

        Tham số:
            project_key (str): Key của project muốn tạo issue mới. Có thể bao gồm cả chữ và số.
            summary (str): Tóm tắt issue.
            description (str): Mô tả issue.
            issue_type (str): Loại issue, không nói gì mặc định là Task.
            due_date (str): Ngày đến hạn deadline, có thể rỗng.
            priority (str): Mức độ ưu tiên của task.
            assignee_displayname (str): Display name của người được giao (đảm nhiệm) task này.

        Trả về:
            Trả về đầy đủ thông tin như dưới return formatted, phải đúng format, không diễn giải hay cắt bớt gì cả.
        """
        result = create_issue(self.access_token, self.cloud_id, self.domain, project_key, summary, description, issue_type, due_date, assignee_displayname, priority)

        formatted = (
            f"- Project Key: {project_key}\n"
            f"- Issue Key: {result.get('issue_key', '')}\n"
            f"- Link Issue: {result.get('issue_url', '')}\n"
            f"- Tóm tắt: {result.get('summary', '')}\n"
            f"- Mô tả: {result.get('description', '')}\n"
            f"- Loại: {result.get('issue_type', '')}\n"
            f"- Ngày đến hạn: {result.get('due_date', 'N/A')}\n"
            f"- Mức độ ưu tiên: {result.get('priority', 'N/A')}\n"
            f"- Người đảm nhiệm: {result.get('assignee_displayname', 'Không có')}\n"
        ) 

        return f"✅ Đã tạo issue thành công!\n{formatted}"

    def assign_jira_issue(self, issue_key: str, assignee_displayname: str):
        """
        Giao task cho user từ issue_key, assignee_displayname

        Hàm này nhận vào key của một issue trong Jira cùng assignee_displayname của người được giao task.

        Tham số:
            issue_key (str): Key của issue muốn giao task. Có thể bao gồm cả chữ và số.
            assignee_displayname (str): Display name của người được giao (đảm nhiệm) task này.

        Trả về:
            Một chuỗi chứa thông tin sau khi giao task.
        """
        result = assign_issue(self.access_token, self.cloud_id, issue_key, assignee_displayname)

        formatted = (
            f"- Project Key: {result.get('project_key', '')}\n"
            f"- Issue Key: {result.get('issue_key', '')}\n"
            f"- Tóm tắt: {result.get('summary', '')}\n"
            f"- Mô tả: {result.get('description', '')}\n"
            f"- Loại: {result.get('issue_type', '')}\n"
            f"- Ngày đến hạn: {result.get('due_date', 'N/A')}\n"
            f"- Người đảm nhiệm: {result.get('assignee_displayname', 'Không có')}\n"
        ) 

        return f"✅ Đã giao task thành công!\n{formatted}"

    def transition_jira_issue(self, issue_key: str, transition_name: str):
        """
        Chuyển trạng thái cho task với issue_key sang transition_name

        Hàm này nhận vào key của một issue trong Jira cùng transition_name của task.

        Tham số:
            issue_key (str): Key của issue muốn giao task. Có thể bao gồm cả chữ và số.
            transition_name (str): Tên của trạng thái task.

        Trả về:
            Một chuỗi chứa thông tin sau khi chuyển trạng thái task.
        """
        result = transition_issue(self.access_token, self.cloud_id, issue_key, transition_name)

        formatted = (
            f"- Issue Key: {result.get('issue_key', '')}\n"
            f"- Trạng thái: {result.get('status', '')}\n"
            f"- Tóm tắt: {result.get('summary', '')}\n"
            f"- Người đảm nhiệm: {result.get('assignee', 'Không có')}\n"
        ) 

        return f"✅ Đã chuyển trạng thái task thành công!\n{formatted}"

    def get_jira_comments(self, issue_key: str):
        """
        Lấy danh sách các bình luận (comments) của task với issue_key.

        Hàm này nhận vào key của một issue trong Jira.

        Tham số:
            issue_key (str): Key của issue muốn lấy comments. Có thể bao gồm cả chữ và số.

        Trả về:
            Chuỗi MarkdownV2 hoặc plaint text để gửi qua Telegram. Không được viết thêm gì nữa.
        """
        result = get_comments(self.access_token, self.cloud_id, issue_key)

        if not result:
            return "Task hiện tại chưa có bình luận!"

        def escape_markdown(text: str) -> str:
            chars_to_escape = r"\_*[]()~`>#+-=|{}.!-"
            for ch in chars_to_escape:
                text = text.replace(ch, f"\\{ch}")
            return text

        def format_markdown_table(issues: list[dict]) -> str:
            MAX_LENGTH = 22

            headers = ["ID", "Author", "Comment", "Created At"]
            col_widths = {
                "id": max(len("ID"), max((len(issue["id"]) for issue in issues), default=0)),
                "author": max(len("Author"), max((len(issue["author"]) for issue in issues), default=0)),
                "body": MAX_LENGTH,            
                "created": max(len("Created At"), max((len(issue.get("created") or "") for issue in issues), default=0)),
            }

            def pad(text: str, width: int) -> str:
                return text + ' ' * (width - len(text))

            lines = []

            lines.append(
                f"{pad('ID', col_widths['id'])} | "
                f"{pad('Author', col_widths['author'])} | "
                f"{pad('Comment', col_widths['body'])}"
            )

            lines.append(
                f"{'-' * (col_widths['id'] + 1)}|"
                f"{'-' * (col_widths['author'] + 2)}|"
                f"{'-' * (col_widths['body'] + 1)}"
            )

            for issue in issues:
                id = pad(escape_markdown(issue['id']), col_widths['id'])

                comment_raw = issue['body']
                if len(comment_raw) > MAX_LENGTH:
                    comment_raw = comment_raw[:MAX_LENGTH - 3] + "..."
                body = pad(escape_markdown(comment_raw), col_widths['body'])

                author = pad(escape_markdown(issue['author']), col_widths['author'])

                lines.append(
                    f"{id} | {author} | {body}"
                )

            table = "\n".join(lines)
            return f"Đây là danh sách bình luận:```\n{table}\n```"

        return format_markdown_table(result)
    
    def create_jira_comment(self, issue_key: str, comment: str):
        """
        Tạo bình luận (comment) mới của task từ issue_key và comment

        Hàm này nhận vào key của một issue trong Jira và comment cho issue đó.

        Tham số:
            issue_key (str): Key của issue muốn comment. Có thể bao gồm cả chữ và số.
            comment (str): Nội dung bình luận (comment)

        Trả về:
            Một chuỗi chứa thông tin sau khi tạo comment cho issue.
        """
        result = add_comment(self.access_token, self.cloud_id, issue_key, comment)

        formatted = (
            f"- Issue Key: {result.get('issue_key', '')}\n"
            f"- Comment ID: {result.get('comment_id', '')}\n"
            f"- Nội dung: {result.get('comment', '')}\n"
        ) 

        return f"✅ Đã tạo bình luận cho task thành công!\n{formatted}"

    def edit_jira_comment(self, issue_key: str, comment_id: int, new_comment: str):
        """
        Chỉnh sửa bình luận (comment) - comment_id của task issue_key với nội dung mới new_comment

        Hàm này nhận vào key của một issue trong Jira, comment_id và comment cho issue đó.

        Tham số:
            issue_key (str): Key của issue muốn comment. Có thể bao gồm cả chữ và số.
            comment_id (int): Comment id muốn chỉnh sửa
            new_comment (str): Nội dung comment mới

        Trả về:
            Một chuỗi chứa thông tin sau khi chỉnh sửa comment.
        """
        result = edit_comment(self.access_token, self.cloud_id, issue_key, comment_id, new_comment)

        formatted = (
            f"- Issue Key: {result.get('issue_key', '')}\n"
            f"- Comment ID: {result.get('comment_id', '')}\n"
            f"- Nội dung: {result.get('new_comment', '')}\n"
        ) 

        return f"✅ Đã chỉnh sửa bình luận cho task thành công!\n{formatted}"

    def attach_file_to_jira_issue(self, issue_key: str) -> str:
        """
        Đính kèm file (ảnh, tài liệu, ...) vào Jira issue

        Args:
            issue_key (str): Key của issue muốn đính kèm file

        Returns:
            str: Nội dung phản hồi người dùng
        """
        file_path = getattr(self, "file_path", None)
        file_name = getattr(self, "file_name", "file")

        if not file_path:
            return "Không tìm thấy file để đính kèm."

        try:
            add_attachment(self.access_token, self.cloud_id, issue_key, file_path, file_name)
            return f"✅ Đã đính kèm file cho issue {issue_key.upper()} thành công!"
        except Exception as e:
            return f"Gặp lỗi khi đính kèm file: {str(e)}"
    
    def get_confluence_page_info(self, page_id: str):
        """
        Lấy ra chi tiết thông tin và đầy đủ TOÀN BỘ NỘI DUNG của một Confluence Page từ page_id, có chứa nội dung đầy đủ. Bên trong nội dung các page sẽ chứa các tài liệu cần thiết cho công việc.
        
        Args:
            page_id (str): ID của page cần lấy thông tin. Một danh sách các page (tên, kèm ID) có thể lấy được từ hàm get_confluence_page_list.

        Returns:
             Một chuỗi chứa thông tin chi tiết, bao gồm toàn bộ nội dung của page được yêu cầu.
        """
        return str(get_page_by_id_v2(self.access_token, self.cloud_id, page_id))
    
    def get_confluence_page_list(self):
        """
        Lấy ra ID và tên của các page chứa nội dung tài liệu có thể truy cập được trong Confluence. ID cần thiết để sử dụng get_confluence_page_info sẽ nằm ở đây.
        Sử dụng hàm này khi cần tìm kiếm các page phù hợp với nội dung cụ thể, rồi lựa chọn từ trong số các page có thể truy cập.
        
        Returns:
             Một chuỗi chứa thông tin chi tiết, bao gồm tên ID của mọi page có thể truy cập được.
        """
        return str(get_all_page_ids_and_titles_v2(self.access_token, self.cloud_id))
    
    def get_task_related_info_from_query(self, query: str):
        """
        Lấy ra các chunk tài liệu liên quan đến một query cụ thể
        
        Args:
            query (str): Câu hỏi/vấn đề/từ khoá cụ thể để tìm kiếm thông tin. Hãy viết như một câu hỏi tìm kiếm thông tin trên Google. Không thể là ID của task nội bộ.
        
        Returns:
            Các chunk thông tin được trả về, liên quan đến câu hỏi/vấn đề/từ khoá cụ thể đã cho
        """
        
        vectordb = VectorDatabase(collection_name=self.user_projects)
        return vectordb.perform_search(query)
        
        

    def reformat_chat_history( 
            raw_chat_history: List[Dict[str, str]]
        ) -> List[genai_types.Content]:
        """
        Parses a list of dictionaries into a list of Gemini API Content objects.

        This function takes a chat history in a simple dictionary format and
        converts it into a list of `genai.types.Content` objects, mapping
        the 'bot' role to 'model' for Gemini API compatibility.

        Args:
            raw_ chat_history: A list of dictionaries, where each dictionary must have
                        a "role" (either "user" or "bot") and a "message" key.

        Returns:
            A list of `genai.types.Content` objects ready for the Gemini API.
            Returns an empty list if google.generativeai is not available
            or if input is malformed.
        """
        gemini_history = []

        for message in raw_chat_history:
            role = message.get("role")
            text = message.get("message")

            if not role or not text:
                print(f"Skipping invalid message (missing role or message): {message}")
                continue

            # Map 'bot' role to 'model'
            if role.lower() == "bot":
                gemini_role = "model"
            elif role.lower() == "user":
                gemini_role = "user"
            else:
                print(f"Skipping message with unknown role '{role}': {message}")
                continue

            # Create the Content and Part objects
            gemini_history.append(genai_types.Content(
                role=gemini_role,
                parts=[genai_types.Part(text=text)],
            ))

        return gemini_history

    def chat_function(self, new_message, 
                            chat_history: list = None, 
                            functions: list[GeminiFunction, callable] = None, 
                            config: dict = config):
        """
        Initiates or continues a chat with the Gemini model, supporting function calling.

        It prepares the tools based on the provided GeminiFunction objects and sends
        the new message to the model. If no chat object is provided, it starts a
        new chat, potentially using the provided history.

        Args:
            new_message (str): The new message/prompt to send to the model.
            chat_history (list, optional): A list of previous messages to initialize the chat with,
                                        if `chat_object` is None. Defaults to None.
            functions (list[GeminiFunction], optional): A list of `GeminiFunction` objects
                                                        representing the available tools/functions
                                                        for the model to call. Defaults to None.

        Returns:
            tuple: A tuple containing:
                - chat_object (Chat): The (potentially new) chat object with the updated history.
                - chat_history (list): The complete, updated chat history from the chat object.
        """
        if functions:
            # Prepare the tools from the GeminiFunction objects
            config.update({
                "tools": [
                    f.get_tool() if isinstance(f, GeminiFunction) else f
                    for f in functions
                    if isinstance(f, GeminiFunction) or callable(f)
                ]
            })
        else: 
            # Prepare the tools from the GeminiFunction objects
            config.update({
                "tools": [
                    f.get_tool() if isinstance(f, GeminiFunction) else f
                    for f in self.functions
                    if isinstance(f, GeminiFunction) or callable(f)
                ]
            })
        config.update({"system_instruction": self.system_message})
        if chat_history and type(chat_history[0]) != genai_types.Content:
            chat_history = ChatAgent.reformat_chat_history(chat_history)

        chat_object = ChatAgent.client.chats.create(model = ChatAgent.model,
                                history = chat_history) #placeholder
        
        response = chat_object.send_message(new_message, config = config, )
        print("LOG:", chat_object._curated_history)
        return response, chat_object._curated_history


if __name__ == "__main__":
    chat_agent = ChatAgent(user_id="1021777")
    
    raw_chat_history = [
        {
            "role": "user",
            "message": "hihi"
        },
        {
            "role": "bot",
            "message": "API Gemini hiện chưa sẵn sàng, vui lòng thử lại sau."
        },
        {
            "role": "user",
            "message": "ok nha"
        },
        {
            "role": "bot",
            "message": "API Gemini hiện chưa sẵn sàng, vui lòng thử lại sau."
        },
    ]
    
    response, chat_history = chat_agent.chat_function("Jira issue 1111-1P nhắc đến mã gì ấy nhỉ", 
                                                      chat_history=raw_chat_history, 
                                                      functions=[
                                                          chat_agent.get_confluence_page_info, 
                                                          chat_agent.get_jira_issue_detail
                                                      ])
    print(response.candidates[0].content.parts[0].text)
    # print("###################################")
    # print(chat_history)
    print("###################################")
    response, chat_history = chat_agent.chat_function("Có", 
                                                      chat_history=chat_history, 
                                                      functions=[
                                                          chat_agent.get_confluence_page_info, 
                                                          chat_agent.get_jira_issue_detail
                                                      ])
    print(response.candidates[0].content.parts[0].text)
    print("###################################")
    # print(chat_history)
    
    
    
    
    