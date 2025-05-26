from google import genai
from google.genai import types as genai_types
from google.genai.chats import Chat
from utils.function_declaration import GeminiFunction, confluence_function
import os
from dotenv import load_dotenv

import asyncio
# Only run this block for Gemini Developer API
load_dotenv()
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
model = "gemini-2.0-flash"
config = {"temperature": 0}



def reformat_chat_history(raw_chat_history: list = None):
    raise NotImplementedError #do later

def chat_with_function_calling(new_message, chat_object: Chat = None, chat_history: list = None, functions: list[GeminiFunction] = None):
    """
    Initiates or continues a chat with the Gemini model, supporting function calling.

    It prepares the tools based on the provided GeminiFunction objects and sends
    the new message to the model. If no chat object is provided, it starts a
    new chat, potentially using the provided history.

    Args:
        new_message (str): The new message/prompt to send to the model.
        chat_object (Chat, optional): An existing `Chat` object to continue the conversation.
                                      If None, a new chat will be started. Defaults to None.
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
        config["tools"] = [f.get_tool() for f in functions]
    else: config = None

    if chat_object is None:
        chat_object = client.chats.create(model = model,
                            history = chat_history) #placeholder
    else:
        pass
    chat_object.send_message(new_message, config = config)

    return chat_object, chat_object._curated_history


if __name__ == "__main__":
    print(chat_with_function_calling("Hello, what is 1+1?")[1])
    print("*"*20)
    print(chat_with_function_calling("Hello, what is 1+1?", functions=[confluence_function])[1])
    print("*"*20)
    print(chat_with_function_calling("Get me the Pikachu page from the Pokemon space on Confluence", functions=[confluence_function])[1])
    