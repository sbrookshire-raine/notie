import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect

# --- 1. PASTE YOUR DROPBOX CODES HERE ---
APP_KEY = 'mixh8ti2bvh323m'
APP_SECRET = 'gftnxj3odab4y78'
# ----------------------------------------

def get_refresh_token():
    """
    This helper script authorizes your app and gets the permanent Refresh Token.
    """
    auth_flow = DropboxOAuth2FlowNoRedirect(
        APP_KEY, 
        APP_SECRET, 
        token_access_type='offline' 
    )

    authorize_url = auth_flow.start()
    
    print("-" * 40)
    print("1. Go to this URL in your browser:")
    print(authorize_url)
    print("-" * 40)
    
    auth_code = input("2. Click 'Allow' (twice if asked), copy the code, and paste it here: ").strip()
    
    try:
        oauth_result = auth_flow.finish(auth_code)
        print("\nSUCCESS! Here is your configuration for Streamlit:")
        print("-" * 40)
        print("[dropbox]")
        print(f'app_key = "{APP_KEY}"')
        print(f'app_secret = "{APP_SECRET}"')
        print(f'refresh_token = "{oauth_result.refresh_token}"')
        print("-" * 40)
        print("Copy the block above and paste it into your Streamlit Secrets.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_refresh_token()