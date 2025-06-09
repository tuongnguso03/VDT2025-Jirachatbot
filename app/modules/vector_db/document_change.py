import os
from fastapi import APIRouter
from pydantic import BaseModel
from .vector_db import VectorDatabase
from dotenv import load_dotenv
from atlassian import Confluence
import requests, json, re
import html
doc_router = APIRouter()

load_dotenv()

class DocumentChangeRequest(BaseModel):
    space_key: str
    page_ID: str
    
    
def _format_page_details_v2(page_data: dict) -> dict:
    if not page_data:
        return {}
    body_info = page_data.get("body", {})
    body_view_value = body_info.get("view", {}).get("value") if "view" in body_info else None
    links_info = page_data.get("_links", {})
    base_link_url = links_info.get("base", "")
    web_ui_path = links_info.get("webui", "")
    full_web_ui_link = f"{base_link_url}{web_ui_path}" if base_link_url and web_ui_path else \
                       (f"{base_link_url}/pages/{page_data.get('id')}" if base_link_url and not web_ui_path else None)

    return {
        "id": page_data.get("id"),
        "title": page_data.get("title"),
        "parent_id": page_data.get("parentId"),
        "content": body_view_value,
        "url": full_web_ui_link,
    }

def admin_get_page(page_id: str):
    cloud_id = "122d270d-f780-4621-b27d-1989a54e38e5"
    username = "metalwallcrusher@gmail.com"
    confluence_admin_api = os.environ.get("JIRA_ADMIN_API")

    confluence = Confluence(
        url=f'https://api.atlassian.com/ex/confluence/{cloud_id}/wiki/',
        username=username,
        password=confluence_admin_api,)
    api_v2_path = f"/api/v2/pages/{page_id}"
    target_url = f"{confluence.url.rstrip('/')}{api_v2_path}"

    params = {"body-format": "view"}

    try:
        response = confluence.session.get(target_url, params=params)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
        page_data = response.json()
        
        # Extract the base URL for web links if available, otherwise, it might be an issue.
        confluence_site_base_url = page_data.get("_links", {}).get("base", "")
        if not confluence_site_base_url:
             print(f"Warning: '_links.base' not found in API response for page {page_id}. Web URLs may be incomplete.")

        return _format_page_details_v2(page_data)
    except requests.exceptions.HTTPError as http_err:
        error_message = str(http_err)
        try:
            error_details = http_err.response.json() # Assuming error response is JSON
            error_message = f"Status: {http_err.response.status_code} {http_err.response.reason}, Details: {error_details}"
        except json.JSONDecodeError: # If error response is not JSON
            error_message = f"Status: {http_err.response.status_code} {http_err.response.reason}, Body: {http_err.response.text}"
        raise Exception(f"Failed to get page ID '{page_id}' using V2 API (HTTPError): {error_message}") from http_err
    except Exception as e:
        raise Exception(f"Failed to get page ID '{page_id}' using V2 API (General Error): {str(e)}") from e
    


@doc_router.post("/document_change")
def document_change(request: DocumentChangeRequest):
    vectorDB = VectorDatabase(collection_name=request.space_key)

    

    
    page_id = request.page_ID
    page_content = admin_get_page(page_id)["content"]
    
    page_content = html.unescape(page_content)
    clean = re.compile('<.*?>')
    page_content = re.sub(clean, '', page_content)
    # page_content = re.sub(r'[^a-zA-Z\s]', '', page_content)
    
    vectorDB.update_document(page_content, document_name=page_id)
    vectorDB.client.close()
    return "update successful"

if __name__ == "__main__":
    print(admin_get_page("65849"))