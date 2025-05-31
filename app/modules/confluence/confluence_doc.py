from atlassian import Confluence
import requests
import json
# unicodedata might be useful for search term normalization if you extend search capabilities
# import unicodedata
# datetime and pytz might be useful if you deal with page versions, last modified dates etc.
# from datetime import datetime
# import pytz

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
        cloud=True 
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
        # Catch any other exceptions
        raise Exception(f"Failed to get current Confluence user (General Error): {str(e)}") from e


def _format_space_details_v2(space_data: dict, site_base_url: str) -> dict:
    """
    Helper function to format Confluence space details from API v2 response.
    site_base_url is the base URL for web links (e.g., "https://your-domain.atlassian.net/wiki")
    """
    if not space_data:
        return {}

    links_info = space_data.get("_links", {})
    web_ui_path = links_info.get("webui", "")
    # If site_base_url already ends with /wiki and web_ui_path starts with /display, it might be okay.
    # Or if web_ui_path is relative to the site_base_url.
    # Example: base="https://foo.atlassian.net/wiki", webui="/display/SPACEKEY" -> full link.
    full_web_ui_link = f"{site_base_url.rstrip('/')}{web_ui_path}" if site_base_url and web_ui_path else None
    
    # Description (plain and view) might not be in the default response, would require expansion if available
    description_plain = space_data.get("description", {}).get("plain", {}).get("value")
    description_view = space_data.get("description", {}).get("view", {}).get("value")


    return {
        "id": space_data.get("id"),
        "key": space_data.get("key"),
        "name": space_data.get("name"),
        "type": space_data.get("type"),
        "status": space_data.get("status"),
        "homepage_id": space_data.get("homepageId"),
        "description_plain": description_plain,
        "description_view": description_view,
        "icon_path": space_data.get("icon", {}).get("path"),
        "url": full_web_ui_link,
        "_links": links_info # Keep all links for flexibility
    }

def get_all_spaces_v2(access_token: str, cloud_id: str, limit_per_page: int = 50):
    """
    Lấy danh sách tất cả các space từ Confluence sử dụng API v2, xử lý pagination.
    - limit_per_page: Số lượng space lấy trong mỗi request (max 100 for spaces).
    """
    confluence = get_confluence_client(access_token, cloud_id)
    print(get_current_confluence_user(confluence))
    
    all_spaces_details = []
    
    # The Confluence client's URL is `https://api.atlassian.com/ex/confluence/{cloud_id}/wiki`
    # The V2 API path is `/api/v2/spaces`
    api_v2_base_path = "/api/v2/spaces"
    current_url = f"{confluence.url.rstrip('/')}{api_v2_base_path}"
    
    params = {"limit": limit_per_page}
    page_num = 1

    while current_url:
        print(f"Fetching page {page_num} of spaces from: {current_url} with params: {params if page_num ==1 else {k:v for k,v in params.items() if k=='cursor'}}")
        try:
            response = confluence.session.get(current_url, params=params if page_num == 1 else {k:v for k,v in params.items() if k=='cursor'}) # Only pass cursor for subsequent requests
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
            data = response.json()

            # The base URL for constructing web links is usually in the main _links of the response collection
            site_base_url = data.get("_links", {}).get("base", "")
            if not site_base_url:
                 print(f"Warning: '_links.base' (site URL) not found in API response for spaces list. Web URLs may be incomplete.")

            results = data.get("results", [])
            for space_item in results:
                all_spaces_details.append(_format_space_details_v2(space_item, site_base_url))
            
            # Pagination: Check for the 'next' link
            next_link_path = data.get("_links", {}).get("next")
            if next_link_path:
                from urllib.parse import urlparse, urlunparse
                parsed_original_url = urlparse(confluence.url) # This is https://api.atlassian.com/ex/confluence/{cloud_id}/wiki
                current_url = urlunparse((parsed_original_url.scheme, parsed_original_url.netloc, next_link_path, '', '', ''))

                params = {} # Clear old params, cursor is in the URL now
                page_num += 1
            else:
                current_url = None # No more pages

        except requests.exceptions.HTTPError as http_err:
            error_message = str(http_err)
            try:
                error_details = http_err.response.json()
                error_message = f"Status: {http_err.response.status_code} {http_err.response.reason}, Details: {error_details}"
            except json.JSONDecodeError:
                error_message = f"Status: {http_err.response.status_code} {http_err.response.reason}, Body: {http_err.response.text}"
            raise Exception(f"Failed to get spaces using V2 API (HTTPError on page {page_num}): {error_message}") from http_err
        except Exception as e:
            raise Exception(f"Failed to get spaces using V2 API (General Error on page {page_num}): {str(e)}") from e
            
    return all_spaces_details

# --- Example Usage ---
def main_confluence_v2_test():
    # Replace with your actual token, cloud_id, and a test page_id
    # Ensure token has scopes like: read:confluence-content.all or read:page:confluence
    ACCESS_TOKEN = "eyJraWQiOiJhdXRoLmF0bGFzc2lhbi5jb20tQUNDRVNTLTk0ZTczYTkwLTUxYWQtNGFjMS1hOWFjLWU4NGUwNDVjNDU3ZCIsImFsZyI6IlJTMjU2In0.eyJqdGkiOiJkOGJiOWIwYi1mMTYxLTQzMjktODU2My0xZDA3YjRmOGM5OTciLCJzdWIiOiI3MTIwMjA6MDhjN2RhNWMtNzZhMi00M2IxLTk3MGItY2FhYzVkZTJjMmQwIiwibmJmIjoxNzQ4NjkwNDUzLCJpc3MiOiJodHRwczovL2F1dGguYXRsYXNzaWFuLmNvbSIsImlhdCI6MTc0ODY5MDQ1MywiZXhwIjoxNzQ4Njk0MDUzLCJhdWQiOiJJM2VaZEU2aE9PVHkwUld2OHU1MVVCeDByUTFFNDBJNCIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS9ydGkiOiI0MmE2MmIxMC02MjM2LTQ2ODktYmM4ZS05ZTZlYWY5ZTY2NGIiLCJzY29wZSI6Im1hbmFnZTpqaXJhLXByb2plY3Qgb2ZmbGluZV9hY2Nlc3MgcmVhZDphY2NvdW50IHJlYWQ6Y29uZmx1ZW5jZS1jb250ZW50LmFsbCByZWFkOmNvbmZsdWVuY2UtY29udGVudC5wZXJtaXNzaW9uIHJlYWQ6Y29uZmx1ZW5jZS1jb250ZW50LnN1bW1hcnkgcmVhZDpjb25mbHVlbmNlLXNwYWNlLnN1bW1hcnkgcmVhZDpjb25mbHVlbmNlLXVzZXIgcmVhZDpqaXJhLXVzZXIgcmVhZDpqaXJhLXdvcmsgcmVhZDptZSByZWFkb25seTpjb250ZW50LmF0dGFjaG1lbnQ6Y29uZmx1ZW5jZSB3cml0ZTpqaXJhLXdvcmsiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vdWp0IjoiNzAwZDY5MTQtM2VmMS00NzdlLWJmYTQtZDNkZTMyM2MzODgwIiwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL2F0bF90b2tlbl90eXBlIjoiQUNDRVNTIiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL3N5c3RlbUFjY291bnRJZCI6IjcxMjAyMDowYjBjYTYyNS0yNDk2LTQzZmUtYTcxOC1jNzNjZDlkZGUxMzUiLCJodHRwczovL2lkLmF0bGFzc2lhbi5jb20vc2Vzc2lvbl9pZCI6IjJhMWFmZDg0LWZhZTQtNGE5YS04Nzc2LTcyODVkZTg2YTgxZiIsImNsaWVudF9pZCI6IkkzZVpkRTZoT09UeTBSV3Y4dTUxVUJ4MHJRMUU0MEk0IiwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL2ZpcnN0UGFydHkiOmZhbHNlLCJodHRwczovL2F0bGFzc2lhbi5jb20vdmVyaWZpZWQiOnRydWUsInZlcmlmaWVkIjoidHJ1ZSIsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS9wcm9jZXNzUmVnaW9uIjoidXMtd2VzdC0yIiwiaHR0cHM6Ly9pZC5hdGxhc3NpYW4uY29tL3JlZnJlc2hfY2hhaW5faWQiOiJJM2VaZEU2aE9PVHkwUld2OHU1MVVCeDByUTFFNDBJNC03MTIwMjA6MDhjN2RhNWMtNzZhMi00M2IxLTk3MGItY2FhYzVkZTJjMmQwLTAyMjVmNDUzLTUwZmQtNGEwMy1iYjZhLTdiNWQyNjlmMWYwZCIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9lbWFpbERvbWFpbiI6ImdtYWlsLmNvbSIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS8zbG8iOnRydWUsImh0dHBzOi8vaWQuYXRsYXNzaWFuLmNvbS92ZXJpZmllZCI6dHJ1ZSwiaHR0cHM6Ly9hdGxhc3NpYW4uY29tL29hdXRoQ2xpZW50SWQiOiJJM2VaZEU2aE9PVHkwUld2OHU1MVVCeDByUTFFNDBJNCIsImh0dHBzOi8vYXRsYXNzaWFuLmNvbS9zeXN0ZW1BY2NvdW50RW1haWxEb21haW4iOiJjb25uZWN0LmF0bGFzc2lhbi5jb20iLCJodHRwczovL2F0bGFzc2lhbi5jb20vc3lzdGVtQWNjb3VudEVtYWlsIjoiYmRjMjhhNzAtODNhNS00YmU2LWJmOTMtZjVmMTQ5NzhhNmFkQGNvbm5lY3QuYXRsYXNzaWFuLmNvbSJ9.GNWylLZ_So-eeMZ3F_QwW1p9OMX72J3ZQU4W6yYU5vFjJeiS2oDP1eHyaKSIYUTJc-uuwTbqIvG0r_f0XRrwZ7onHWyTrnyIDBMfFxKP6TV5NDvRsrJ8gFbgy6LMjc1o-EAhLKzC0HBWSt7AhqPL2kHBHvdh1LrwkE7-5I3hWmszwdHWR_5qoQV8J5R3Fpir4yL50pPy4uctn2cqA8ClyB-pOTVUBWhC2ynDSAtLev1FHGt2TuNHMhUuVWFTICz5YIxK7R7J2Fy38IaQxF2vhs4VdorB20YVU6UllivXf0D6gFnJrV441KcLdPzav5ECJ_pqRCQelottQgpOG2KGRw"
    CLOUD_ID = "122d270d-f780-4621-b27d-1989a54e38e5" # The one from your Atlassian site

    print(get_all_spaces_v2(ACCESS_TOKEN, CLOUD_ID, limit_per_page=5))

if __name__ == "__main__":
    # You might want to comment this out if just importing the module
    main_confluence_v2_test()
    pass