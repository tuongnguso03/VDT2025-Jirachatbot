from google import genai
from google.genai import types as genai_types
from .utils.function_declaration import GeminiFunction
import os
from dotenv import load_dotenv
from typing import List, Dict

from modules.confluence.confluence_doc import get_page_by_id_v2, get_all_page_ids_and_titles_v2
from modules.jira.jira_task import get_all_issues, get_today_issues, get_issue_detail, get_worklogs, log_work, create_issue, assign_issue, transition_issue, get_comments, add_comment, edit_comment, add_attachment

import json
import requests
import mimetypes
import re
# Only run this block for Gemini Developer API
load_dotenv()

class ChatAgent:
    """
    The chat agent class. Handle everything chat. Or that sort.
    """
    client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    model = "gemini-1.5-flash"
    config = {"temperature": 0}
    
    def __init__(self, user_id: str, access_token: str, cloud_id: str, domain: str):
        self.user_id = user_id
        self.access_token = access_token
        self.cloud_id = cloud_id
        self.domain = domain
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
            self.get_confluence_page_list]

    def get_jira_issues(self):
        """
        Lấy ra danh sách tasks (công việc) của người dùng
        
        Hàm này trả về thông tin danh sách tasks (công việc) của người dùng đó.

        Trả về:
            Một list chuỗi chứa thông tin danh sách tasks được yêu cầu.
        """
        result = get_all_issues(self.access_token, self.cloud_id)

        if not result:
            return "🎉 Bạn không có công việc nào đang xử lý!"

        formatted = "📋 Danh sách công việc đang xử lý:\n\n"

        for idx, issue in enumerate(result, start=1):
            key = issue.get("key", "N/A")
            summary = issue.get("summary", "Không có tiêu đề")
            type = issue.get("type", "N/A")
            status = issue.get("status", "Không rõ trạng thái")
            deadline = issue.get("deadline", "Chưa có hạn")

            formatted += (
                f"{idx}. *{key}* - {summary}\n"
                f"    - Loại: {type}\n"
                f"    - Trạng thái: `{status}`\n"
                f"    - Deadline: {deadline}\n\n"
            )

        return formatted

    def get_jira_issues_today(self):
        """
        Lấy ra danh sách tasks (công việc) của người dùng ngày hôm nay.
        
        Hàm này trả về thông tin danh sách tasks (công việc) của người dùng đó ngày hôm nay.

        Trả về:
            Một list chuỗi chứa thông tin danh sách tasks được yêu cầu.
        """
        result = get_today_issues(self.access_token, self.cloud_id)

        if not result:
            return "🎉 Bạn không có công việc nào đang xử lý!"

        formatted = "📋 Danh sách công việc đang xử lý:\n\n"

        for idx, issue in enumerate(result, start=1):
            key = issue.get("key", "N/A")
            summary = issue.get("summary", "Không có tiêu đề")
            type = issue.get("type", "N/A")
            status = issue.get("status", "Không rõ trạng thái")
            deadline = issue.get("deadline", "Chưa có hạn")

            formatted += (
                f"{idx}. *{key}* - {summary}\n"
                f"    - Loại: {type}\n"
                f"    - Trạng thái: `{status}`\n"
                f"    - Deadline: {deadline}\n\n"
            )

        return formatted

    def get_jira_issue_detail(self, issue_key: str):
        """
        Lấy ra chi tiết của một task từ issue_key
        
        Hàm này nhận vào key của một issue trong Jira và trả về thông tin chi tiết của issue đó.

        Tham số:
            issue_key (str): key của issue cần lấy thông tin. Có thể bao gồm cả chữ và số.
            
        Trả về dict gồm: thông tin mô tả issue dạng chuỗi
        """
        result = get_issue_detail(self.access_token, self.cloud_id, issue_key)

        
        attachment_urls = [att.get("content_url") for att in result.get("attachments", []) if att.get("content_url")]

        formatted = (
            f"- Dự án: {result.get('project', '')}\n"
            f"- Jira Issue: {result.get('key', '')}\n"
            f"- Tóm tắt: {result.get('summary', '')}\n"
            f"- Mô tả: {result.get('description', '')}\n"
            f"- Loại: {result.get('type', '')}\n"
            f"- Deadline: {result.get('duedate', 'Không có')}\n"
            f"- Trạng thái: {result.get('status', '')}\n"
            f"- Người thực hiện: {result.get('assignee', 'Chưa gán')}\n"
            f"- Người tạo: {result.get('reporter', '')}\n"
            f"- Mức độ ưu tiên: {result.get('priority', '')}\n"
        )

        if attachment_urls:
            formatted += f"- Attachments: {json.dumps(attachment_urls)}\n"

        return formatted
            
    
    def get_jira_log_works(self, issue_key: str):
        """
        Lấy ra danh sách worklog của một task từ issue_key

        Hàm này nhận vào key của một issue trong Jira và trả về danh sách worklog cho issue đó.

        Tham số:
            issue_key (str): key của issue cần lấy thông tin. Có thể bao gồm cả chữ và số.

        Trả về:
            Một chuỗi chứa thông tin worklog.
        """
        result = get_worklogs(self.access_token, self.cloud_id, issue_key)
        formatted = "📋 Danh sách công việc đang xử lý:\n\n"

        for idx, issue in enumerate(result, start=1):
            id = issue.get("id", "N/A")
            author = issue.get("author", "N/A")
            time_spent = issue.get("time_spent", "N/A")
            started = issue.get("started", "N/A")
            comment = issue.get("comment", "Không có comment")

            formatted += (
                f"- WorklogID: {id}\n"
                f"- Người log work: {author}\n"
                f"- Thời gian làm việc: {time_spent}\n"
                f"- Thời gian bắt đầu làm: {started}\n"
                f"- Comment: {comment}\n"
            )

        return formatted

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
            Một chuỗi chứa thông tin worklog sau khi log work.
        """
        result = log_work(self.access_token, self.cloud_id, issue_key, time_spend, comment, date)

        formatted = (
            f"- Jira Issue: {result.get('issue_key', '')}\n"
            f"- WorklogID: {result.get('id', '')}\n"
            f"- Người log work: {result.get('author', '')}\n"
            f"- Thời gian làm việc: {result.get('time_spend', '')}\n"
            f"- Thời gian bắt đầu làm: {result.get('started', '')}\n"
            f"- Comment: {result.get('comment', 'Không có')}\n"
        ) 

        return formatted
    
    def create_jira_issue(self, project_key: str, summary: str, description: str, issue_type: str, due_date: str, assignee_displayname: str):
        """
        Tạo mới (task) issue từ project_key, summary, description, issue_type, assignee_displayname, due_date

        Hàm này nhận vào key của một project trong Jira, ngày, tóm tắt, mô tả, loại issue, ngày đến hạn, displayname của người được giao task.

        Tham số:
            project_key (str): Key của project muốn tạo issue mới. Có thể bao gồm cả chữ và số.
            summary (str): Tóm tắt issue.
            description (str): Mô tả issue.
            issue_type (str): Loại issue, không nói gì mặc định là Task.
            due_date (str): Ngày đến hạn deadline, có thể rỗng.
            assignee_displayname (str): Tên của người được giao (đảm nhiệm) task này, có thể rỗng.

        Trả về:
            Một chuỗi chứa thông tin task sau khi tạo task.
        """
        result = create_issue(self.access_token, self.cloud_id, self.domain, project_key, summary, description, issue_type, due_date, assignee_displayname)

        formatted = (
            f"- Project Key: {project_key}\n"
            f"- Issue Id: {result.get('issue_id', '')}\n"
            f"- Issue Key: {result.get('issue_key', '')}\n"
            f"- Link Issue: {result.get('issue_url', '')}\n"
            f"- Tóm tắt: {result.get('summary', '')}\n"
            f"- Mô tả: {result.get('description', '')}\n"
            f"- Loại: {result.get('issue_type', '')}\n"
            f"- Ngày đến hạn: {result.get('due_date', 'N/A')}\n"
            f"- AssigneeId: {result.get('assignee_id', 'Không có')}\n"
            f"- Người đảm nhiệm: {result.get('assignee_displayname', 'Không có')}\n"
        ) 

        return formatted

    def assign_jira_issue(self, issue_key: str, assignee_displayname: str):
        """
        Giao task cho user từ issue_key, assignee_displayname

        Hàm này nhận vào key của một issue trong Jira cùng displayname của người được giao task.

        Tham số:
            issue_key (str): Key của issue muốn giao task. Có thể bao gồm cả chữ và số.
            assignee_displayname (str): Tên của người được giao (đảm nhiệm) task này.

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
            f"- AssigneeId: {result.get('assignee_id', 'Không có')}\n"
            f"- Người đảm nhiệm: {result.get('assignee_displayname', 'Không có')}\n"
        ) 

        return formatted

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

        return formatted

    def get_jira_comments(self, issue_key: str):
        """
        Lấy danh sách các bình luận (comments) của task với issue_key

        Hàm này nhận vào key của một issue trong Jira.

        Tham số:
            issue_key (str): Key của issue muốn lấy comments. Có thể bao gồm cả chữ và số.

        Trả về:
            Một chuỗi chứa thông tin sau khi lấy danh sách comments.
        """
        result = get_comments(self.access_token, self.cloud_id, issue_key)
        formatted = ""

        for idx, issue in enumerate(result, start=1):
            id = issue.get("id")
            author = issue.get("author")
            body = issue.get("body")
            created = issue.get("created")
            updated = issue.get("updated")

            formatted += (
                f"{idx}. *{id}* - {body}\n"
                f"    - Người tạo: {author}\n"
                f"    - Tạo lúc: `{created}`\n"
                f"    - Chỉnh sửa lúc: {updated}\n\n"
            )

        return formatted
    
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

        return formatted
    
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

        return formatted

    def attach_file_to_jira_issue(self, message: str) -> str:
        """
        Đính kèm file vào Jira issue (tìm issue key từ message)

        Args:
            message (str): Tin nhắn chứa issue key (VD: "vui lòng đính kèm file vào VDT-123")

        Returns:
            str: Nội dung phản hồi người dùng
        """
        file_path = getattr(self, "file_path", None)
        file_name = getattr(self, "file_name", "file")

        if not file_path:
            return "Không tìm thấy file để đính kèm."

        match = re.search(r"[A-Z]+-\d+", message)
        if not match:
            return "Không tìm thấy mã issue trong tin nhắn."

        issue_key = match.group(0)

        try:
            return add_attachment(self.access_token, self.cloud_id, issue_key, file_path, file_name)
        except Exception as e:
            return f"Gặp lỗi khi đính kèm file: {str(e)}"

        
    
    def get_confluence_page_info(self, page_id: str):
        """
        Lấy ra chi tiết thông tin của một Confluence Page từ page_id, có chứa nội dung đầy đủ. Bên trong nội dung các page sẽ chứa các tài liệu cần thiết cho công việc.
        
        Args:
            page_id (str): ID của page cần lấy thông tin. Một danh sách các page (tên, kèm ID) có thể lấy được từ hàm get_confluence_page_list.

        Returns:
             Một chuỗi chứa thông tin chi tiết, bao gồm nội dung của page được yêu cầu.
        """
        return str(get_page_by_id_v2(self.access_token, self.cloud_id, page_id))
    
    def get_confluence_page_list(self):
        """
        Lấy ra ID và tên của các page chứa nội dung tài liệu có thể truy cập được trong Confluence. ID cần thiết để sử dụng get_confluence_page_info sẽ nằm ở đây.
        """
        return str(get_all_page_ids_and_titles_v2(self.access_token, self.cloud_id))

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
        
        if chat_history and type(chat_history[0]) != genai_types.Content:
            chat_history = ChatAgent.reformat_chat_history(chat_history)

        chat_object = ChatAgent.client.chats.create(model = ChatAgent.model,
                                history = chat_history) #placeholder
        
        response = chat_object.send_message(new_message, config = config)
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
    
    
    
    
    