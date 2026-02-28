from typing import Protocol
import logging
from typing import Optional
import ytmusicapi
from pycookiecheat import chrome_cookies
import json
import os
import logging
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# Constants for cache files
COOKIE_CACHE = "cookies.json"
BROWSER_JSON = "browser.json"


class AccountInfo(BaseModel):
    # Field aliases map the JSON key to your Python variable
    account_name: str = Field(alias="accountName")
    channel_handle: str = Field(alias="channelHandle")
    account_photo_url: str = Field(alias="accountPhotoUrl")

# Init logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)

def load_cached_cookies() -> Optional[dict]:
    """Return cached cookies dict if available, otherwise None."""
    if os.path.exists(COOKIE_CACHE):
        try:
            with open(COOKIE_CACHE, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    logging.info(f"[success] Loaded cookies from {COOKIE_CACHE}")
                    return data
        except Exception as e:
            logging.warning(f"Failed to read cached cookies: {e}")
    return None


def save_cookies(cookies_dict: dict):
    """Persist cookies dict to disk for reuse."""
    try:
        with open(COOKIE_CACHE, "w") as f:
            json.dump(cookies_dict, f)
        logging.info(f"Cookies saved to {COOKIE_CACHE}")
    except Exception as e:
        logging.error(f"Failed to save cookies: {e}")


def auto_login():
    """Automates the login process by extracting cookies from Chrome and bypassing the auth type check.

    If a cookie cache exists we prefer that data and avoid re-extraction from the browser.
    """

    # 1. Try load from cache first
    cookies_dict = load_cached_cookies()
    if cookies_dict is None:
        # 2. Get the real cookies from your Mac
        try:
            url = "https://music.youtube.com"
            cookies_dict = chrome_cookies(url)
            if not cookies_dict:
                logging.error("[error] No cookies found for the specified URL.")
                return None
            # check if it is a dict instead of a list
            if not isinstance(cookies_dict, dict):
                logging.error("Unexpected cookie format: Expected a dict.")
                return None
            
            save_cookies(cookies_dict)
        except Exception as e:
            logging.error(f"Cookie extraction failed: {e}")
            return None

    cookie_string = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])

    # 2. Reconstruct the raw headers
    # We add a fake Authorization header that contains the magic word 'SAPISIDHASH'
    # This tricks determine_auth_type() into returning AuthType.BROWSER
    raw_headers = (
        "Accept: */*\n"
        "Accept-Language: en-US,en;q=0.9\n"
        "Content-Type: application/json\n"
        "X-Goog-AuthUser: 0\n"
        "x-origin: https://music.youtube.com\n"
        "Authorization: SAPISIDHASH dummy_hash_to_bypass_check\n"  # <--- THE FIX
        f"Cookie: {cookie_string}"
    )

    try:
        # 3. Official setup call
        # Now it will pass the internal check and identify as 'BROWSER'
        ytmusicapi.setup(filepath="browser.json", headers_raw=raw_headers)

        # 4. Initialize
        yt = ytmusicapi.YTMusic("browser.json")

        logging.info("Verifying authentication...")
        yt.get_library_playlists(limit=1)
        logging.info("[success] The check has been bypassed.")
        return yt

    except Exception as e:
        logging.error(f"Setup failed: {e}")
        return None


# Execution
yt = auto_login()

if yt:
    print("\n--- Running Final Verification ---")
    try:
        # 1. Get your account name/info
        data = yt.get_account_info()
        info = AccountInfo(**data)
    # log all info
        logging.info(f"Account Info: {info}")
        print(f"👤 Account: {info.account_name}")

        # 2. Fetch the titles of your last 3 played songs
        history = yt.get_history()
        print("\n🎵 Your Recent History:")
        for i, track in enumerate(history[:3], 1):
            title = track.get("title")
            artist = track.get("artists")[0].get("name")
            print(f"  {i}. {title} - {artist}")

        # 3. Check your library size
        library = yt.get_library_playlists(limit=5)
        logging.info(f"✅ Access Confirmed: Found {len(library)} playlists in your library.")

    except Exception as e:
        logging.error(f"Verification failed: {e}")
        logging.warning(
            "This usually means the cookies found were expired or for the wrong account."
        )
