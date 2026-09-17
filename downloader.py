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

VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".webm", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ============================================================
# URL HELPERS
# ============================================================

def instagram_parts(url: str):
    return [
        part
        for part in urlparse(url).path.strip("/").split("/")
        if part
    ]


def extract_shortcode(url: str):
    parts = [p.lower() for p in instagram_parts(url)]

    for marker in ("reel", "reels", "p", "tv"):
        if marker in parts:
            index = parts.index(marker)

            if index + 1 < len(parts):
                return instagram_parts(url)[index + 1]

    return None


def extract_username(url: str):
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

    if parts[0].lower() in reserved:
        return None

    return parts[0]


def is_reel_url(url: str):
    parts = [p.lower() for p in instagram_parts(url)]

    return (
        "reel" in parts
        or "reels" in parts
    )


def is_post_url(url: str):
    parts = [p.lower() for p in instagram_parts(url)]

    return (
        "p" in parts
        or "tv" in parts
    )


def is_profile_url(url: str):
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


def api_get(session, endpoint, params=None):
    response = session.get(
        f"{BASE_URL}/{endpoint.lstrip('/')}",
        headers=api_headers(),
        params=params or {},
        timeout=120,
    )

    if response.status_code == 401:
        raise RuntimeError(
            "RapidAPI authentication failed. "
            "Check RAPIDAPI_KEY."
        )

    if response.status_code == 403:
        raise RuntimeError(
            "RapidAPI rejected the request. "
            "Check the API subscription."
        )

    if response.status_code == 407:
        raise RuntimeError(
            "RapidAPI returned HTTP 407. "
            "The API provider/proxy connection "
            "could not be established."
        )

    if response.status_code == 429:
        raise RuntimeError(
            "RapidAPI rate limit exceeded."
        )

    response.raise_for_status()

    try:
        return response.json()

    except ValueError as exc:
        raise RuntimeError(
            "RapidAPI returned invalid JSON."
        ) from exc


# ============================================================
# JSON SEARCH HELPERS
# ============================================================

def walk(value):
    """
    Recursively walk through dictionaries and lists.
    """

    if isinstance(value, dict):

        yield value

        for child in value.values():
            yield from walk(child)

    elif isinstance(value, list):

        for child in value:
            yield from walk(child)


def first_value(data, keys):
    """
    Find the first value whose key matches one of
    the requested keys.
    """

    keys = {
        key.lower()
        for key in keys
    }

    for obj in walk(data):

        for key, value in obj.items():

            if (
                key.lower() in keys
                and value not in (
                    None,
                    "",
                    [],
                    {},
                )
            ):
                return value

    return None


def find_shortcode_object(data, shortcode):
    """
    Find the media object matching the Instagram shortcode.
    """

    if not shortcode:
        return None

    target = str(shortcode).lower()

    for obj in walk(data):

        for key in (
            "code",
            "shortcode",
            "short_code",
            "media_code",
        ):

            value = obj.get(key)

            if (
                value
                and str(value).lower() == target
            ):
                return obj

        for key in (
            "url",
            "link",
            "permalink",
            "web_url",
        ):

            value = obj.get(key)

            if (
                isinstance(value, str)
                and target in value.lower()
            ):
                return obj

    return None


# ============================================================
# MEDIA URL EXTRACTION
# ============================================================

def best_video_url(obj):
    """
    Return the best available video URL.
    """

    if not isinstance(obj, dict):
        return None

    # Direct video URL fields.
    for key in (
        "video_url",
        "video_url_hd",
        "play_url",
        "download_url",
    ):

        value = obj.get(key)

        if (
            isinstance(value, str)
            and value.startswith("http")
        ):
            return value

    # Instagram-style video_versions.
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
            )

            if (
                not isinstance(url, str)
                or not url.startswith("http")
            ):
                continue

            width = item.get("width") or 0
            height = item.get("height") or 0

            candidates.append(
                (
                    width * height,
                    url,
                )
            )

        if candidates:

            candidates.sort(
                reverse=True
            )

            return candidates[0][1]

    # Search nested dictionaries.
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


def best_image_url(obj):
    """
    Return the best available image URL.
    """

    if not isinstance(obj, dict):
        return None

    for key in (
        "display_url",
        "image_url",
        "thumbnail_url",
        "profile_pic_url_hd",
        "profile_pic_url",
    ):

        value = obj.get(key)

        if (
            isinstance(value, str)
            and value.startswith("http")
        ):
            return value

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

                area = width * height

                if area > best_area:

                    best_area = area
                    best = url

            return best

    return None


def media_url_and_type(obj):
    """
    Prefer video over image.
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
    response = session.get(
        url,
        stream=True,
        timeout=300,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/120 Safari/537.36"
            )
        },
    )

    response.raise_for_status()

    with open(filename, "wb") as file:

        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):

            if chunk:
                file.write(chunk)


# ============================================================
# YT-DLP FALLBACK
# ============================================================

def download_with_ytdlp(
    url,
    temp_dir,
):
    """
    Fallback when RapidAPI doesn't return a
    usable media URL.
    """

    try:
        import yt_dlp

    except ImportError as exc:

        raise RuntimeError(
            "yt-dlp is not installed. "
            "Add yt-dlp to requirements.txt."
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
# PROFILE
# ============================================================

def download_profile(
    session,
    url,
    temp_dir,
):
    username = extract_username(url)

    if not username:

        raise RuntimeError(
            "Invalid Instagram profile URL."
        )

    data = api_get(
        session,
        "/user_info",
        {
            "username": username
        },
    )

    image_url = first_value(
        data,
        (
            "profile_pic_url_hd",
            "hd_profile_pic_url",
            "profile_pic_url",
        ),
    )

    if (
        not isinstance(image_url, str)
        or not image_url.startswith("http")
    ):
        image_url = best_image_url(
            data
        )

    if not image_url:

        raise RuntimeError(
            "Profile picture not found."
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
    Query media_info_v2.

    Try both common parameter names because
    providers can expose slightly different
    parameter names.
    """

    last_error = None

    for parameter in (
        "code",
        "shortcode",
    ):

        try:

            return api_get(
                session,
                "/media_info_v2",
                {
                    parameter: shortcode
                },
            )

        except Exception as exc:

            last_error = exc

    if last_error:
        raise last_error

    return None


# ============================================================
# POST / REEL
# ============================================================

def download_media(
    session,
    url,
    temp_dir,
):
    shortcode = extract_shortcode(url)

    if not shortcode:

        raise RuntimeError(
            "Could not extract Instagram shortcode."
        )

    data = get_media_info(
        session,
        shortcode,
    )

    media = find_shortcode_object(
        data,
        shortcode,
    )

    # Some API responses return the media
    # object directly without a shortcode.
    if media is None:

        possible = []

        for obj in walk(data):

            if (
                best_video_url(obj)
                or best_image_url(obj)
            ):
                possible.append(obj)

        if possible:
            media = possible[0]

    if media is None:

        raise RuntimeError(
            "Media information was not found."
        )

    # ========================================================
    # CAROUSEL
    # ========================================================

    carousel = media.get(
        "carousel_media"
    )

    if isinstance(carousel, list):

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

            files.append(filename)

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
            "No downloadable media URL "
            "was returned."
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
# MAIN FUNCTION
# ============================================================

def download_instagram(
    url: str
):
    """
    Main downloader entry point.

    Supports:

    - Instagram Reels
    - Instagram Posts
    - Instagram TV
    - Instagram profiles
    """

    url = url.strip()

    parsed = urlparse(url)

    if parsed.netloc.lower() not in {
        "instagram.com",
        "www.instagram.com",
        "m.instagram.com",
    }:

        raise ValueError(
            "Invalid Instagram URL."
        )

    temp_dir = tempfile.mkdtemp()

    session = requests.Session()

    try:

        # ----------------------------------------------------
        # PROFILE
        # ----------------------------------------------------

        if is_profile_url(url):

            return download_profile(
                session,
                url,
                temp_dir,
            )

        # ----------------------------------------------------
        # REEL / POST
        # ----------------------------------------------------

        if (
            is_reel_url(url)
            or is_post_url(url)
        ):

            try:

                return download_media(
                    session,
                    url,
                    temp_dir,
                )

            except Exception as api_error:

                # Try yt-dlp if the API cannot
                # provide usable media.

                try:

                    return download_with_ytdlp(
                        url,
                        temp_dir,
                    )

                except Exception:

                    # Keep the original API error.
                    raise api_error

        raise ValueError(
            "Unsupported Instagram URL."
        )

    except Exception:

        # Clean temporary files if the
        # operation fails.

        shutil.rmtree(
            temp_dir,
            ignore_errors=True,
        )

        raise

    finally:

        session.close()