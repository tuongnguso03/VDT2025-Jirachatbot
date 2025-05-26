from google import genai
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
    print(chat_function("Hello, what is 1+1?")[1])
    print("*"*20)
    print(chat_function("Hello, what is 1+1?", functions=[confluence_function])[1])
    print("*"*20)
    response, chat_history = chat_function("Get me the Pikachu page from the Pokemon space on Confluence", functions=[confluence_function])
    print(chat_history)
    print("*"*20)
    print(chat_function("What did I just ask you to do?")[1])
    print("*"*20)
    print(chat_function("Get the Rayquaza page from the same space", functions=[confluence_function])[0] )
    print("*"*20)
    def the_ultimate_function(question: str):
        """
        Gives the answer to life, but nothing else
        
        Args:
            question (str): Your question.
        """
        
        if "life" in question:
            return 424
        else:
            return "Invalid question"
    print(chat_function("Get the Rayquaza page from the Sue space", functions=[confluence_function, the_ultimate_function], config={})[0])
    print("*"*20)
    print(chat_function("Give me the answer to what life is", functions=[confluence_function, the_ultimate_function])[0])
    
    