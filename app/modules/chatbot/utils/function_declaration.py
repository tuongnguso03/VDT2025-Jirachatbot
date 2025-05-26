from google.genai import types as genai_types # Use an alias to avoid conflict if user imports 'types'

class GeminiFunction:
    """
    A wrapper class to simplify the creation of function declarations,
    Tool objects, and GenerateContentConfig for Google's Gemini API.
    """
    def __init__(self, name: str, description: str):
        """
        Initializes a GeminiFunction instance.

        Args:
            name (str): The name of the function.
            description (str): A description of what the function does.
        """
        if not name:
            raise ValueError("Function name cannot be empty.")
        if not description:
            raise ValueError("Function description cannot be empty.")

        self.name = name
        self.description = description
        self._parameters_properties: dict = {}
        self._required_parameters: list[str] = []

    def add_parameter(
        self,
        name: str,
        param_type: str,
        description: str,
        is_required: bool = False,
        items: dict = None,
        enum: list = None
    ) -> 'GeminiFunction':
        """
        Adds a parameter to the function's definition.

        Args:
            name (str): The name of the parameter.
            param_type (str): The type of the parameter (e.g., "string", "integer", "boolean", "array", "object", "number").
            description (str): A description of the parameter.
            is_required (bool, optional): Whether this parameter is required. Defaults to False.
            items (dict, optional): If param_type is "array", this dictionary describes the type of items
                                    in the array (e.g., {"type": "string"}). Defaults to None.
            enum (list, optional): If param_type is "string", this list provides allowed enum values.
                                   Defaults to None.

        Returns:
            GeminiFunction: The instance itself, allowing for method chaining.

        Raises:
            ValueError: If parameter name or description is empty, or if 'items' is not provided for 'array' type.
        """
        if not name:
            raise ValueError("Parameter name cannot be empty.")
        if not description:
            raise ValueError("Parameter description cannot be empty.")
        if param_type == "array" and not items:
            raise ValueError("Parameter of type 'array' must have 'items' specified.")

        param_definition = {
            "type": param_type,
            "description": description,
        }

        if param_type == "array" and items:
            param_definition["items"] = items
        
        if enum and param_type in ["string", "integer", "number"]: # Enums are typically for these types
            param_definition["enum"] = enum

        self._parameters_properties[name] = param_definition
        if is_required:
            if name not in self._required_parameters:
                self._required_parameters.append(name)
        return self

    def get_declaration(self) -> dict:
        """
        Constructs and returns the function declaration dictionary.

        Returns:
            dict: The function declaration suitable for the Gemini API.
        """
        declaration = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": self._parameters_properties,
            },
        }
        if self._required_parameters:
            declaration["parameters"]["required"] = sorted(list(set(self._required_parameters))) # Ensure uniqueness and order
        return declaration

    def get_tool(self) -> genai_types.Tool:
        """
        Creates and returns a genai.types.Tool object for this function.

        Returns:
            genai_types.Tool: The Tool object.
        """
        return genai_types.Tool(function_declarations=[self.get_declaration()])
    

# Will import these functions anyway lul
confluence_function = GeminiFunction("confluence_function",
                                     description='''Takes a document from Confluence for information.'''
                                    ).add_parameter(
                                        "space_name",
                                        param_type="string",
                                        description="The name of the Confluence space of the document",
                                    ).add_parameter(
                                        "document_name",
                                        param_type="string",
                                        description="The name of the document",
                                        is_required=True
                                    )
if __name__ == "__main__":
    print(confluence_function)
    print("*"*10)
    print(confluence_function.get_declaration())
    print("*"*10)
    print(confluence_function.get_tool())
