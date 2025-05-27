from google import genai
from google.genai import types as genai_types
from .utils.function_declaration import GeminiFunction, confluence_function
import os
from dotenv import load_dotenv
from typing import List, Dict

import asyncio
# Only run this block for Gemini Developer API
load_dotenv()
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
model = "gemini-2.0-flash"
config = {"temperature": 0}



def reformat_chat_history(
        raw_chat_history: List[Dict[str, str]]
    ) -> List[genai_types.Content]:
    """
    Parses a list of dictionaries into a list of Gemini API Content objects.

    This function takes a chat history in a simple dictionary format and
    converts it into a list of `genai.types.Content` objects, mapping
    the 'bot' role to 'model' for Gemini API compatibility.

    Args:
        chat_history: A list of dictionaries, where each dictionary must have
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

def chat_function(new_message, 
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
    else: config = None

    chat_object = client.chats.create(model = model,
                            history = chat_history) #placeholder
    
    response = chat_object.send_message(new_message, config = config)

    return response, chat_object._curated_history


if __name__ == "__main__":
    # print(chat_function("Hello, what is 1+1?")[1])
    # print("*"*20)
    # print(chat_function("Hello, what is 1+1?", functions=[confluence_function])[1])
    # print("*"*20)
    # response, chat_history = chat_function("Get me the Pikachu page from the Pokemon space on Confluence", functions=[confluence_function])
    # print(chat_history)
    # print("*"*20)
    # print(chat_function("What did I just ask you to do?")[1])
    # print("*"*20)
    # print(chat_function("Get the Rayquaza page from the same space", functions=[confluence_function])[0] )
    # print("*"*20)
    # def the_ultimate_function(question: str):
    #     """
    #     Gives the answer to life, but nothing else
        
    #     Args:
    #         question (str): Your question.
    #     """
        
    #     if "life" in question:
    #         return 424
    #     else:
    #         return "Invalid question"
    # print(chat_function("Get the Rayquaza page from the Sue space", functions=[confluence_function, the_ultimate_function], config={"temperature": 0, ""})[0])
    # print("*"*20)
    # print(chat_function("Give me the answer to what life is", functions=[confluence_function, the_ultimate_function])[0])
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
    chat_history = reformat_chat_history(raw_chat_history)
    response, chat_history = chat_function("Lặp lại điều m vừa nói, nhưng mà thêm \"bolobala\" ở đầu câu", chat_history=chat_history, functions=[confluence_function])
    print(response.candidates[0].content.parts[0].text)
    print(chat_history)
    
    
    