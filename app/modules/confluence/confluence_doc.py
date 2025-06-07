from atlassian import Confluence
import requests
import json
from urllib.parse import urlparse, urlunparse

def get_confluence_client(access_token: str, cloud_id: str) -> Confluence:
    """
    Tạo đối tượng Confluence client dùng access_token Bearer OAuth 2.0.
    atlassian-python-api chưa hỗ trợ trực tiếp OAuth2 bearer token,
    nên cần khởi tạo session có header Authorization rồi truyền vào Confluence(client=session).
    """
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    })

    base_url = f"https://api.atlassian.com/ex/confluence/{cloud_id}/wiki"
    # Khởi tạo Confluence client với base_url + session tùy chỉnh
    return Confluence(
        url=base_url,
        session=session,
    )

def get_current_confluence_user(confluence: Confluence):
    """
    Lấy thông tin người dùng hiện tại từ Confluence bằng cách gọi API endpoint.
    """
    try:
        # Construct the URL for the 'current user' endpoint
        # The confluence object should have 'url' (base_url) and 'session' attributes
        # e.g., confluence.url might be "https://your-domain.atlassian.net/wiki"
        api_url = f"{confluence.url}/rest/api/user/current"
        
        response = confluence.session.get(api_url)
        
        response.raise_for_status() # Will raise an HTTPError for bad responses (4xx or 5xx)
        
        return response.json()

    except requests.exceptions.HTTPError as http_err:
        error_message = str(http_err)
        try:
            # Try to get JSON error details from the response
            error_details = http_err.response.json()
            error_message = f"Status: {http_err.response.status_code} {http_err.response.reason}, Details: {error_details}"
        except json.JSONDecodeError:
            # If response is not JSON, use the text content
            error_message = f"Status: {http_err.response.status_code} {http_err.response.reason}, Body: {http_err.response.text}"
        raise Exception(f"Failed to get current Confluence user (HTTPError): {error_message}") from http_err
        
    except Exception as e:
        raise Exception(f"Failed to get current Confluence user (General Error): {str(e)}") from e


def _format_page_details_v2(page_data: dict) -> dict:
    if not page_data:
        return {}

    # version_info = page_data.get("version", {})
    body_info = page_data.get("body", {})
    
    # Body content based on what was requested and returned
    body_view_value = body_info.get("view", {}).get("value") if "view" in body_info else None
    # body_adf_value = body_info.get("atlas_doc_format", {}).get("value") if "atlas_doc_format" in body_info else None

    links_info = page_data.get("_links", {})
    base_link_url = links_info.get("base", "") # Should be like https://your-domain.atlassian.net/wiki
    web_ui_path = links_info.get("webui", "")
    full_web_ui_link = f"{base_link_url}{web_ui_path}" if base_link_url and web_ui_path else \
                       (f"{base_link_url}/pages/{page_data.get('id')}" if base_link_url and not web_ui_path else None)


    # Space details if expanded and present
    # space_key = None
    # space_id = page_data.get("spaceId") # This is always present

    return {
        "id": page_data.get("id"),
        # "status": page_data.get("status"),
        "title": page_data.get("title"),
        # "space_id": space_id, 
        "parent_id": page_data.get("parentId"),
        # "author_id": page_data.get("authorId"), # Author of the page object itself
        # "created_at": page_data.get("createdAt"),
        # "version_number": version_info.get("number"),
        # "version_message": version_info.get("message"),
        # "version_minor_edit": version_info.get("minorEdit"),
        # "version_author_id": version_info.get("authorId"), # Author of this specific version
        # "version_created_at": version_info.get("createdAt"),
        "content": body_view_value,
        # "body_atlas_doc_format": body_adf_value,
        "url": full_web_ui_link,
        # "_links": links_info # Keep all links for flexibility
    }

def get_page_by_id_v2(access_token: str, cloud_id: str, page_id: str, 
                      body_format: str = "view"):
    """
    Lấy nội dung của một trang Confluence bằng Page ID sử dụng API v2.
    - body_format: 'view', 'storage', 'atlas_doc_format'.
    - extra_properties: list of additional properties to retrieve if supported by API. (Currently limited in v2 for page by id)
    """
    confluence = get_confluence_client(access_token, cloud_id)
    
    api_v2_path = f"/api/v2/pages/{page_id}"
    target_url = f"{confluence.url.rstrip('/')}{api_v2_path}"

    params = {}
    if body_format:
        params["body-format"] = body_format

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
    
def get_all_page_ids_and_titles_v2(access_token: str, cloud_id: str, 
                                  space_id: str = None, 
                                  status: str = 'current', 
                                  limit_per_page: int = 100):
    """
    Lấy danh sách ID và Tiêu đề của tất cả các trang từ Confluence sử dụng API v2.
    Xử lý pagination.
    
    Args:
        access_token (str): OAuth 2.0 access token.
        cloud_id (str): Cloud ID của instance Atlassian.
        space_id (str, optional): ID của Space để giới hạn tìm kiếm. 
                                  Nếu None, lấy từ tất cả các space có quyền truy cập.
        status (str, optional): Trạng thái của trang để lấy (e.g., 'current', 'draft', 'archived'). 
                                Mặc định là 'current'.
        limit_per_page (int, optional): Số lượng trang lấy trong mỗi request. Max 250.
                                       Mặc định là 100.
    Returns:
        list: Danh sách các dictionary, mỗi dict chứa 'id' và 'title' của trang.
              Trả về list rỗng nếu không có trang nào hoặc có lỗi.
    Raises:
        Exception: Nếu có lỗi trong quá trình gọi API.
    """
    if limit_per_page > 250:
        print("Warning: limit_per_page for pages is typically max 250. Setting to 250.")
        limit_per_page = 250
    
    confluence = get_confluence_client(access_token, cloud_id)
    
    all_pages_summary = []
    
    api_v2_base_path = "/api/v2/pages"
    current_url = f"{confluence.url.rstrip('/')}{api_v2_base_path}"
    
    # Initial parameters
    params = {
        "limit": limit_per_page,
        "status": status,
        "sort": "id" # Sorting by ID for stable pagination
    }
    if space_id:
        params["space-id"] = space_id
        
    page_num = 1
    is_first_request = True

    while current_url:
        request_params = params if is_first_request else {} 
        print(f"Fetching page {page_num} of pages from: {current_url} with params: {request_params if is_first_request else ' (params in URL from next link)'}")
        try:
            response = confluence.session.get(current_url, params=request_params)
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
            data = response.json()

            results = data.get("results", [])
            for page_item in results:
                all_pages_summary.append({
                    "id": page_item.get("id"),
                    "title": page_item.get("title")
                })
            
            # Pagination: Check for the 'next' link
            next_link_path = data.get("_links", {}).get("next")
            if next_link_path:
                parsed_original_url = urlparse(confluence.url)
                current_url = urlunparse((parsed_original_url.scheme, parsed_original_url.netloc, next_link_path, '', '', ''))
                
                is_first_request = False 
                page_num += 1
            else:
                current_url = None 

        except requests.exceptions.HTTPError as http_err:
            error_message = str(http_err)
            try:
                error_details = http_err.response.json()
                error_message = f"Status: {http_err.response.status_code} {http_err.response.reason}, Details: {error_details}"
            except json.JSONDecodeError:
                error_message = f"Status: {http_err.response.status_code} {http_err.response.reason}, Body: {http_err.response.text}"
            raise Exception(f"Failed to get pages (HTTPError on page {page_num}): {error_message}") from http_err
        except Exception as e:
            raise Exception(f"Failed to get pages (General Error on page {page_num}): {str(e)}") from e
    return all_pages_summary

def main_confluence_v2_test():
    ACCESS_TOKEN = "eyJraWQiOiJhdXRoLmF0bGFzc2lhbi5jb20tQUNDRVNTLTk0ZTczYTkwLTUxYWQtNGFjMS1hOWFjLWU4NGUwNDVjNDU3ZCIsImFsZyI6IlJTMjU2In0.eyJqdGkiOiI1Y2E1MDA5Zi01NWJkLTQxMzItOGZmOC1hN2JiNDVhYTFlNzMiLCJzdWIiOiI3MTIwMjA6MDhjN2RhNWMtNzZhMi00M2IxLTk3MGItY2FhYzVkZTJjMmQwIiwibmJmIjoxNzQ4NzEwNDY1LCJpc3MiOiJodHRwczovL2F1dGguYXRsYXNzaWFuLmNvbSIsImlhdCI6MTc0ODcxMDQ2NSwiZXhwIjoxNzQ4NzE0MDY1LCJhdWQiOiJJM2VaZEU2aE9PVHkwUld2OHU1MVVCeDByUTFFNDBJNCIsInNjb3BlIjoibWFuYWdlOmppcmEtcHJvamVjdCBvZmZsaW5lX2FjY2VzcyByZWFkOmFjY291bnQgcmVhZDphbmFseXRpY3MuY29udGVudDpjb25mbHVlbmNlIHJlYWQ6YXBwLWRhdGE6Y29uZmx1ZW5jZSByZWFkOmJsb2dwb3N0OmNvbmZsdWVuY2UgcmVhZDpjb21tZW50OmNvbmZsdWVuY2UgcmVhZDpjb25mbHVlbmNlLWNvbnRlbnQuYWxsIHJlYWQ6Y29uZmx1ZW5jZS1jb250ZW50LnBlcm1pc3Npb24gcmVhZDpjb25mbHVlbmNlLWNvbnRlbnQuc3VtbWFyeSByZWFkOmNvbmZsdWVuY2UtZ3JvdXBzIHJlYWQ6Y29uZmx1ZW5jZS1wcm9wcyByZWFkOmNvbmZsdWVuY2Utc3BhY2Uuc3VtbWFyeSByZWFkOmNvbmZsdWVuY2UtdXNlciByZWFkOmNvbnRlbnQtZGV0YWlsczpjb25mbHVlbmNlIHJlYWQ6Y29udGVudC5tZXRhZGF0YTpjb25mbHVlbmNlIHJlYWQ6Y29udGVudC5wcm9wZXJ0eTpjb25mbHVlbmNlIHJlYWQ6Y29udGVudDpjb25mbHVlbmNlIHJlYWQ6Y3VzdG9tLWNvbnRlbnQ6Y29uZmx1ZW5jZSByZWFkOmRhdGFiYXNlOmNvbmZsdWVuY2UgcmVhZDplbWJlZDpjb25mbHVlbmNlIHJlYWQ6Zm9sZGVyOmNvbmZsdWVuY2UgcmVhZDpqaXJhLXVzZXIgcmVhZDpqaXJhLXdvcmsgcmVhZDptZSByZWFkOnBhZ2U6Y29uZmx1ZW5jZSByZWFkOnNwYWNlLWRldGFpbHM6Y29uZmx1ZW5jZSByZWFkOnNwYWNlLnByb3BlcnR5OmNvbmZsdWVuY2UgcmVhZDpzcGFjZTpjb25mbHVlbmNlIHJlYWQ6dGFzazpjb25mbHVlbmNlIHJlYWQ6dXNlcjpjb25mbHVlbmNlIHJlYWRvbmx5OmNvbnRlbnQuYXR0YWNobWVudDpjb25mbHVlbmNlIHdyaXRlOmppcmEtd29yayIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS9hdGxfdG9rZW5fdHlwZSI6IkFDQ0VTUyIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9zeXN0ZW1BY2NvdW50SWQiOiI3MTIwMjA6MGIwY2E2MjUtMjQ5Ni00M2ZlLWE3MTgtYzczY2Q5ZGRlMTM1IiwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL3Nlc3Npb25faWQiOiIyYTFhZmQ4NC1mYWU0LTRhOWEtODc3Ni03Mjg1ZGU4NmE4MWYiLCJjbGllbnRfaWQiOiJJM2VaZEU2aE9PVHkwUld2OHU1MVVCeDByUTFFNDBJNCIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9maXJzdFBhcnR5IjpmYWxzZSwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL3ZlcmlmaWVkIjp0cnVlLCJ2ZXJpZmllZCI6InRydWUiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vcHJvY2Vzc1JlZ2lvbiI6InVzLXdlc3QtMiIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS91anQiOiI2YjczZDg4OC00NDU1LTQwOWYtYjI4Ni1jNzdjMjZhY2NiNWUiLCJodHRwczovL2F0bGFzc2lhbi5jb20vZW1haWxEb21haW4iOiJnbWFpbC5jb20iLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vcnRpIjoiZjU0NTgxYmItYjliOS00ODcyLWI5NmUtMDE0MWNkZDcwOTk3IiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tLzNsbyI6dHJ1ZSwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL3ZlcmlmaWVkIjp0cnVlLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vcmVmcmVzaF9jaGFpbl9pZCI6IkkzZVpkRTZoT09UeTBSV3Y4dTUxVUJ4MHJRMUU0MEk0LTcxMjAyMDowOGM3ZGE1Yy03NmEyLTQzYjEtOTcwYi1jYWFjNWRlMmMyZDAtNmYzZjc2ZGQtNjU2ZC00MjM2LTkwZjMtZTI3ODA1ODI0YTRlIiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL29hdXRoQ2xpZW50SWQiOiJJM2VaZEU2aE9PVHkwUld2OHU1MVVCeDByUTFFNDBJNCIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9zeXN0ZW1BY2NvdW50RW1haWxEb21haW4iOiJjb25uZWN0LmF0bGFzc2lhbi5jb20iLCJodHRwczovL2F0bGFzc2lhbi5jb20vc3lzdGVtQWNjb3VudEVtYWlsIjoiYmRjMjhhNzAtODNhNS00YmU2LWJmOTMtZjVmMTQ5NzhhNmFkQGNvbm5lY3QuYXRsYXNzaWFuLmNvbSJ9.jSyJPlTSyT3jWSOyzgHaGmvQdDBjsrHqSlbY233SqLPLf3jutK9lVjT7AYMHtLKUA84LkAPVC8J2DtHi7FdBw4Bpr5DSlx25AzbFivP1YfylGj9Le_oNwzEK2f3Vt1rI4ZPOTy_ki6cmDlaHfSYVxiDkCIjlsLyKEGz85_ydlq0V9sM6uO8RAJ1EzTN-zSdCpVDzzTSAluemBNNyd7e1NgITe4QW-rwVR2hl-5AY_tRJVHQYR_QCzYmL0pW0WXXf5XFDYlwQIGrk1WjbBztSVBPErJyDtACivcCNcxYOvf2JP4DrF8FZgejlDfSCi3Nqgny6t-Yu1yxfoQnR2fQniA"
    CLOUD_ID = "122d270d-f780-4621-b27d-1989a54e38e5" # The one from your Atlassian site
    
    print(get_all_page_ids_and_titles_v2(ACCESS_TOKEN, CLOUD_ID))
    
    TEST_PAGE_ID = "65849" 

    print(f"Attempting to get page ID: {TEST_PAGE_ID} using Confluence API V2")
    try:
        page_details_view = get_page_by_id_v2(ACCESS_TOKEN, CLOUD_ID, TEST_PAGE_ID, body_format="view")
        if page_details_view:
            print(str(page_details_view))

        # Get page with storage format
        page_details_storage = get_page_by_id_v2(ACCESS_TOKEN, CLOUD_ID, TEST_PAGE_ID, body_format="storage")
        if page_details_storage:
            print("\n--- Page Details (Storage Format) ---")
            print(f"ID: {page_details_storage['id']}")
            print(f"Title: {page_details_storage['title']}")
            if page_details_storage['body_storage']:
                print(f"Body (Storage - Snippet): {page_details_storage['body_storage']}...")
            else:
                print("Body (Storage): Not available or not requested correctly.")

    except Exception as e:
        print(f"\nLỗi trong quá trình xử lý: {e}")

if __name__ == "__main__":
    # You might want to comment this out if just importing the module
    main_confluence_v2_test()
    pass