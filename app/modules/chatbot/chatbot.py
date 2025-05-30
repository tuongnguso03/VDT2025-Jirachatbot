from google import genai
from google.genai import types as genai_types
from .utils.function_declaration import GeminiFunction
import os
from dotenv import load_dotenv
from typing import List, Dict
from modules.jira.jira_task import get_all_issues, get_today_issues, get_issue_detail
import json
# Only run this block for Gemini Developer API
load_dotenv()


class ChatAgent:
    """
    The chat agent class. Handle everything chat. Or that sort.
    """
    client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    model = "gemini-2.0-flash"
    config = {"temperature": 0}
    
    def __init__(self, user_id: str, access_token: str, cloud_id: str, domain: str):
        self.user_id = user_id
        self.access_token = access_token
        self.cloud_id = cloud_id
        self.domain = domain
        self.functions = [self.get_jira_issues, self.get_jira_issues_today, self.get_confluence_page_info, self.get_jira_issue_detail]

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
            status = issue.get("status", "Không rõ trạng thái")
            deadline = issue.get("deadline", "Chưa có hạn")

            formatted += (
                f"{idx}. *{key}* - {summary}\n"
                f"    - Trạng thái: `{status}`\n"
                f"    - Deadline: {deadline}\n\n"
            )

        return formatted

    def get_jira_issues_today(self):
        """
        Lấy ra danh sách tasks (công việc) của người dùng ngày hôm này
        
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
            status = issue.get("status", "Không rõ trạng thái")
            deadline = issue.get("deadline", "Chưa có hạn")

            formatted += (
                f"{idx}. *{key}* - {summary}\n"
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

        Trả về:
            Một chuỗi chứa thông tin chi tiết của issue được yêu cầu.
        """
        result = get_issue_detail(self.access_token, self.cloud_id, issue_key)

        formatted = (
            f"   - Dự án: {result.get('project', '')}"
            f"   - Jira Issue: {result.get('key', '')}\n"
            f"   - Tóm tắt: {result.get('summary', '')}\n"
            f"   - Mô tả: {result.get('description', '')}\n"
            f"   - Tạo lúc: {result.get('created', '')}\n"
            f"   - Cập nhật: {result.get('updated', '')}\n"
            f"   - Deadline: {result.get('duedate', 'Không có')}\n"
            f"   - Trạng thái: {result.get('status', '')}\n"
            f"   - Người thực hiện: {result.get('assignee', 'Chưa gán')}\n"
            f"   - Người tạo: {result.get('reporter', '')}\n"
            f"   - Mức độ ưu tiên: {result.get('priority', '')}\n"
        ) 

        return formatted
    
    def get_confluence_page_info(self, page_id: str):
        """
        Get a Confluence page from the ID.
        
        This function takes an ID of a Confluence page, and returns the information of such issue.
        
        Args:
            page_id (str): ID of the required page

        Returns:
            A string contains the information from the page required.
        """
        ###DUMMY
        return f"The code is {page_id}-{self.user_id}-PAGE-{page_id}"

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
    
    
    
    
    