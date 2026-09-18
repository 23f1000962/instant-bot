import os
import re
import shutil
import tempfile
from urllib.parse import urlparse

import requests


# ============================================================
# CONFIGURATION
# ============================================================

RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]

RAPIDAPI_HOST = os.getenv(
    "RAPIDAPI_HOST",
    "instagram-scraper2.p.rapidapi.com",
)

BASE_URL = f"https://{RAPIDAPI_HOST}"

VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mov",
    ".webm",
    ".mkv",
}

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
}


# ============================================================
# URL HELPERS
# ============================================================

def instagram_parts(url: str):
    """
    Return the path components of an Instagram URL.
    """

    return [
        part
        for part in urlparse(url).path.strip("/").split("/")
        if part
    ]


def extract_shortcode(url: str):
    """
    Extract shortcode from:
        /reel/ABC123/
        /reels/ABC123/
        /p/ABC123/
        /tv/ABC123/
    """

    parts = instagram_parts(url)

    lower_parts = [
        part.lower()
        for part in parts
    ]

    for marker in (
        "reel",
        "reels",
        "p",
        "tv",
    ):

        if marker in lower_parts:

            index = lower_parts.index(marker)

            if index + 1 < len(parts):
                return parts[index + 1]

    return None


def extract_username(url: str):
    """
    Extract username from a profile URL.

    Example:
        https://www.instagram.com/instagram/
        -> instagram
    """

    parts = instagram_parts(url)

    if not parts:
        return None

    reserved = {
        "reel",
        "reels",
        "p",
        "tv",
        "stories",
        "explore",
        "accounts",
        "direct",
        "about",
        "developer",
        "web",
    }

    username = parts[0]

    if username.lower() in reserved:
        return None

    return username


def is_reel_url(url: str):
    parts = [
        part.lower()
        for part in instagram_parts(url)
    ]

    return (
        "reel" in parts
        or "reels" in parts
    )


def is_post_url(url: str):
    parts = [
        part.lower()
        for part in instagram_parts(url)
    ]

    return (
        "p" in parts
        or "tv" in parts
    )


def is_profile_url(url: str):
    """
    Determine whether the URL is a simple profile URL.
    """

    parts = instagram_parts(url)

    if len(parts) != 1:
        return False

    reserved = {
        "reel",
        "reels",
        "p",
        "tv",
        "stories",
        "explore",
        "accounts",
        "direct",
        "about",
        "developer",
        "web",
    }

    return parts[0].lower() not in reserved


# ============================================================
# RAPIDAPI
# ============================================================

def api_headers():
    return {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST,
    }


def api_get(
    session,
    endpoint,
    params=None,
):
    """
    Make a GET request to RapidAPI.
    """

    url = (
        f"{BASE_URL}/"
        f"{endpoint.lstrip('/')}"
    )

    response = session.get(
        url,
        headers=api_headers(),
        params=params or {},
        timeout=120,
    )

    # --------------------------------------------------------
    # Authentication
    # --------------------------------------------------------

    if response.status_code == 401:

        raise RuntimeError(
            "RapidAPI authentication failed. "
            "Check RAPIDAPI_KEY."
        )

    # --------------------------------------------------------
    # Subscription / permission
    # --------------------------------------------------------

    if response.status_code == 403:

        raise RuntimeError(
            "RapidAPI rejected the request. "
            "Check your Instagram API subscription."
        )

    # --------------------------------------------------------
    # Proxy/provider connection
    # --------------------------------------------------------

    if response.status_code == 407:

        raise RuntimeError(
            "RapidAPI returned HTTP 407. "
            "The API provider/proxy connection "
            "could not be established."
        )

    # --------------------------------------------------------
    # Rate limit
    # --------------------------------------------------------

    if response.status_code == 429:

        raise RuntimeError(
            "RapidAPI rate limit exceeded."
        )

    response.raise_for_status()

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    try:

        return response.json()

    except ValueError as exc:

        raise RuntimeError(
            "RapidAPI returned invalid JSON."
        ) from exc


# ============================================================
# GENERIC JSON WALKER
# ============================================================

def walk(value):
    """
    Recursively walk through dictionaries/lists.

    This allows the downloader to work with slightly
    different response envelopes from the API.
    """

    if isinstance(value, dict):

        yield value

        for child in value.values():
            yield from walk(child)

    elif isinstance(value, list):

        for child in value:
            yield from walk(child)


def first_value(
    data,
    keys,
):
    """
    Find the first non-empty value whose key matches
    one of the requested keys.
    """

    wanted = {
        key.lower()
        for key in keys
    }

    for obj in walk(data):

        for key, value in obj.items():

            if (
                key.lower() in wanted
                and value not in (
                    None,
                    "",
                    [],
                    {},
                )
            ):
                return value

    return None


# ============================================================
# MEDIA OBJECT SEARCH
# ============================================================

def find_media_object(
    data,
    shortcode=None,
):
    """
    Find the media object in the API response.

    First attempts to match the shortcode.
    Otherwise looks for an object containing media URLs.
    """

    # --------------------------------------------------------
    # First: match shortcode
    # --------------------------------------------------------

    if shortcode:

        target = shortcode.lower()

        for obj in walk(data):

            for key in (
                "code",
                "shortcode",
                "short_code",
                "media_code",
            ):

                value = obj.get(key)

                if (
                    value is not None
                    and str(value).lower() == target
                ):
                    return obj

    # --------------------------------------------------------
    # Second: look for obvious media objects
    # --------------------------------------------------------

    candidates = []

    for obj in walk(data):

        if not isinstance(obj, dict):
            continue

        if (
            best_video_url(obj)
            or best_image_url(obj)
        ):
            candidates.append(obj)

    if candidates:
        return candidates[0]

    return None


# ============================================================
# VIDEO URL EXTRACTION
# ============================================================

def best_video_url(obj):
    """
    Find the best available video URL.
    """

    if not isinstance(obj, dict):
        return None

    # --------------------------------------------------------
    # Direct URL fields
    # --------------------------------------------------------

    for key in (
        "video_url",
        "video_url_hd",
        "video_url_standard",
        "play_url",
        "download_url",
        "video",
    ):

        value = obj.get(key)

        if (
            isinstance(value, str)
            and value.startswith("http")
        ):
            return value

    # --------------------------------------------------------
    # Common video version structures
    # --------------------------------------------------------

    for key in (
        "video_versions",
        "video_versions2",
        "videos",
    ):

        versions = obj.get(key)

        if not isinstance(versions, list):
            continue

        candidates = []

        for item in versions:

            if not isinstance(item, dict):
                continue

            url = (
                item.get("url")
                or item.get("src")
                or item.get("video_url")
            )

            if (
                not isinstance(url, str)
                or not url.startswith("http")
            ):
                continue

            width = item.get("width") or 0
            height = item.get("height") or 0

            try:
                area = int(width) * int(height)

            except Exception:
                area = 0

            candidates.append(
                (
                    area,
                    url,
                )
            )

        if candidates:

            candidates.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            return candidates[0][1]

    # --------------------------------------------------------
    # Nested search
    # --------------------------------------------------------

    for nested in walk(obj):

        if nested is obj:
            continue

        for key in (
            "video_url",
            "play_url",
            "download_url",
        ):

            value = nested.get(key)

            if (
                isinstance(value, str)
                and value.startswith("http")
            ):
                return value

    return None


# ============================================================
# IMAGE URL EXTRACTION
# ============================================================

def best_image_url(obj):
    """
    Find the best available image URL.
    """

    if not isinstance(obj, dict):
        return None

    # --------------------------------------------------------
    # Direct image fields
    # --------------------------------------------------------

    for key in (
        "profile_pic_url_hd",
        "hd_profile_pic_url",
        "profile_pic_url",
        "display_url",
        "image_url",
        "thumbnail_url",
        "thumbnail_src",
        "display_src",
        "image",
    ):

        value = obj.get(key)

        if (
            isinstance(value, str)
            and value.startswith("http")
        ):
            return value

    # --------------------------------------------------------
    # image_versions2
    # --------------------------------------------------------

    versions = obj.get(
        "image_versions2"
    )

    if isinstance(versions, dict):

        candidates = versions.get(
            "candidates"
        )

        if isinstance(candidates, list):

            best = None
            best_area = -1

            for item in candidates:

                if not isinstance(item, dict):
                    continue

                url = item.get("url")

                if (
                    not isinstance(url, str)
                    or not url.startswith("http")
                ):
                    continue

                width = item.get("width") or 0
                height = item.get("height") or 0

                try:
                    area = (
                        int(width)
                        * int(height)
                    )

                except Exception:
                    area = 0

                if area > best_area:

                    best_area = area
                    best = url

            if best:
                return best

    # --------------------------------------------------------
    # display_resources
    # --------------------------------------------------------

    resources = obj.get(
        "display_resources"
    )

    if isinstance(resources, list):

        candidates = []

        for item in resources:

            if not isinstance(item, dict):
                continue

            url = item.get(
                "src"
            ) or item.get(
                "url"
            )

            if (
                not isinstance(url, str)
                or not url.startswith("http")
            ):
                continue

            width = item.get("config_width") or 0
            height = item.get("config_height") or 0

            try:
                area = (
                    int(width)
                    * int(height)
                )

            except Exception:
                area = 0

            candidates.append(
                (
                    area,
                    url,
                )
            )

        if candidates:

            candidates.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            return candidates[0][1]

    return None


# ============================================================
# MEDIA URL + TYPE
# ============================================================

def media_url_and_type(obj):
    """
    Prefer video when both video and image are available.
    """

    video = best_video_url(obj)

    if video:
        return video, ".mp4"

    image = best_image_url(obj)

    if image:
        return image, ".jpg"

    return None, None


# ============================================================
# FILE DOWNLOAD
# ============================================================

def download_file(
    session,
    url,
    filename,
):
    """
    Download a remote media URL to disk.
    """

    response = session.get(
        url,
        stream=True,
        timeout=300,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120 Safari/537.36"
            )
        },
    )

    response.raise_for_status()

    with open(
        filename,
        "wb",
    ) as file:

        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):

            if chunk:
                file.write(chunk)


# ============================================================
# PROFILE PICTURE
# ============================================================

def download_profile(
    session,
    url,
    temp_dir,
):
    """
    Download Instagram profile picture.

    API:
        GET /user_info
        user_name=<username>
    """

    username = extract_username(url)

    if not username:

        raise RuntimeError(
            "Invalid Instagram profile URL."
        )

    # --------------------------------------------------------
    # IMPORTANT:
    # The API screenshot shows:
    #
    # user_name *
    #
    # NOT username.
    # --------------------------------------------------------

    data = api_get(
        session,
        "/user_info",
        {
            "user_name": username,
        },
    )

    # --------------------------------------------------------
    # Try HD profile picture first
    # --------------------------------------------------------

    image_url = first_value(
        data,
        (
            "profile_pic_url_hd",
            "hd_profile_pic_url",
            "profile_pic_url",
        ),
    )

    # --------------------------------------------------------
    # Fallback to generic image extraction
    # --------------------------------------------------------

    if (
        not isinstance(image_url, str)
        or not image_url.startswith("http")
    ):

        image_url = best_image_url(
            data
        )

    if not image_url:

        raise RuntimeError(
            "Profile picture was not found "
            "in the UserInfo response."
        )

    safe_username = re.sub(
        r"[^A-Za-z0-9_.-]",
        "_",
        username,
    )

    filename = os.path.join(
        temp_dir,
        f"{safe_username}_profile.jpg",
    )

    download_file(
        session,
        image_url,
        filename,
    )

    return [filename]


# ============================================================
# MEDIA INFO
# ============================================================

def get_media_info(
    session,
    shortcode,
):
    """
    Get information about a single Instagram
    post/reel.

    API screenshot confirms:

        GET MediaInfo_v2

        short_code *
    """

    if not shortcode:

        raise RuntimeError(
            "Instagram shortcode is missing."
        )

    # IMPORTANT:
    # Exact parameter from your API screenshot:
    #
    # short_code
    #
    # NOT:
    # code
    # shortcode

    return api_get(
        session,
        "/media_info_v2",
        {
            "short_code": shortcode,
        },
    )


# ============================================================
# CAROUSEL MEDIA
# ============================================================

def get_carousel_items(media):
    """
    Extract carousel items from several common
    Instagram response formats.
    """

    if not isinstance(media, dict):
        return []

    possible_keys = (
        "carousel_media",
        "carousel",
        "items",
        "children",
        "edge_sidecar_to_children",
    )

    for key in possible_keys:

        value = media.get(key)

        # Direct list
        if isinstance(value, list):
            return value

        # GraphQL-style:
        #
        # {
        #   "edges": [
        #       {"node": {...}}
        #   ]
        # }
        if isinstance(value, dict):

            edges = value.get(
                "edges"
            )

            if isinstance(edges, list):

                items = []

                for edge in edges:

                    if not isinstance(edge, dict):
                        continue

                    node = edge.get(
                        "node"
                    )

                    if isinstance(node, dict):
                        items.append(node)

                if items:
                    return items

    return []


# ============================================================
# DOWNLOAD POST / REEL
# ============================================================

def download_media(
    session,
    url,
    temp_dir,
):
    """
    Download a single Instagram post or Reel.

    Uses:
        /media_info_v2
        short_code=<shortcode>
    """

    shortcode = extract_shortcode(url)

    if not shortcode:

        raise RuntimeError(
            "Could not extract Instagram shortcode "
            "from the URL."
        )

    # --------------------------------------------------------
    # API request
    # --------------------------------------------------------

    data = get_media_info(
        session,
        shortcode,
    )

    # --------------------------------------------------------
    # Locate media object
    # --------------------------------------------------------

    media = find_media_object(
        data,
        shortcode,
    )

    if media is None:

        raise RuntimeError(
            "Media information was not found "
            "in the API response."
        )

    # ========================================================
    # CAROUSEL
    # ========================================================

    carousel = get_carousel_items(
        media
    )

    if carousel:

        files = []

        for index, item in enumerate(
            carousel,
            start=1,
        ):

            media_url, extension = (
                media_url_and_type(item)
            )

            if not media_url:
                continue

            filename = os.path.join(
                temp_dir,
                f"{shortcode}_{index}{extension}",
            )

            download_file(
                session,
                media_url,
                filename,
            )

            files.append(
                filename
            )

        if files:
            return files

    # ========================================================
    # SINGLE MEDIA
    # ========================================================

    media_url, extension = (
        media_url_and_type(media)
    )

    if not media_url:

        raise RuntimeError(
            "No downloadable media URL was returned "
            "by MediaInfo_v2."
        )

    filename = os.path.join(
        temp_dir,
        f"{shortcode}{extension}",
    )

    download_file(
        session,
        media_url,
        filename,
    )

    return [filename]


# ============================================================
# YT-DLP FALLBACK
# ============================================================

def download_with_ytdlp(
    url,
    temp_dir,
):
    """
    Fallback downloader.

    Used if RapidAPI does not return a usable
    media URL.
    """

    try:

        import yt_dlp

    except ImportError as exc:

        raise RuntimeError(
            "yt-dlp is not installed."
        ) from exc

    output = os.path.join(
        temp_dir,
        "%(id)s.%(ext)s",
    )

    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "retries": 3,
        "socket_timeout": 60,
    }

    with yt_dlp.YoutubeDL(
        options
    ) as ydl:

        info = ydl.extract_info(
            url,
            download=True,
        )

        files = []

        # ----------------------------------------------------
        # requested_downloads
        # ----------------------------------------------------

        requested = (
            info.get(
                "requested_downloads"
            )
            or []
        )

        for item in requested:

            path = item.get(
                "filepath"
            )

            if (
                path
                and os.path.isfile(path)
            ):
                files.append(path)

        # ----------------------------------------------------
        # Normal output path
        # ----------------------------------------------------

        if not files:

            path = ydl.prepare_filename(
                info
            )

            if os.path.isfile(path):
                files.append(path)

        if not files:

            raise RuntimeError(
                "yt-dlp did not produce a file."
            )

        return files


# ============================================================
# MAIN DOWNLOAD FUNCTION
# ============================================================

def download_instagram(
    url,
):
    """
    Main entry point used by messages.py.

    Supported:

        Instagram Reel
        Instagram post
        Instagram video
        Instagram image
        Instagram carousel
        Instagram profile picture
    """

    if not isinstance(url, str):
        raise RuntimeError(
            "Invalid Instagram URL."
        )

    url = url.strip()

    if "instagram.com" not in url.lower():

        raise RuntimeError(
            "This is not an Instagram URL."
        )

    temp_dir = tempfile.mkdtemp(
        prefix="instagram_"
    )

    session = requests.Session()

    try:

        # ====================================================
        # PROFILE PICTURE
        # ====================================================

        if is_profile_url(url):

            try:

                return download_profile(
                    session,
                    url,
                    temp_dir,
                )

            except Exception:

                # Profile picture fallback through
                # yt-dlp is generally not useful, so
                # preserve the original API error.
                raise

        # ====================================================
        # POST / REEL
        # ====================================================

        try:

            return download_media(
                session,
                url,
                temp_dir,
            )

        except Exception as rapidapi_error:

            # ------------------------------------------------
            # Try yt-dlp fallback.
            #
            # Do not hide RapidAPI errors such as 401,
            # 403, 407 or 429 if yt-dlp also fails.
            # ------------------------------------------------

            try:

                return download_with_ytdlp(
                    url,
                    temp_dir,
                )

            except Exception as ytdlp_error:

                raise RuntimeError(
                    "RapidAPI download failed: "
                    f"{rapidapi_error}. "
                    "yt-dlp fallback also failed: "
                    f"{ytdlp_error}"
                ) from rapidapi_error

    except Exception:

        # Remove temporary directory on failure.
        shutil.rmtree(
            temp_dir,
            ignore_errors=True,
        )

        raise

    finally:

        session.close()