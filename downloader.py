import os
import re
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
    "mp4",
    "m4v",
    "mov",
    "webm",
    "mkv",
}

IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "gif",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def instagram_parts(url: str):
    """
    Return the path components of an Instagram URL.
    """

    return [
        part.lower()
        for part in urlparse(url).path.strip("/").split("/")
        if part
    ]


def extract_shortcode(url: str):
    """
    Extract Instagram shortcode from:

        /reel/ABC123/
        /reels/ABC123/
        /p/ABC123/
        /tv/ABC123/
    """

    parts = instagram_parts(url)

    for content_type in ("reel", "reels", "p", "tv"):
        if content_type in parts:
            index = parts.index(content_type)

            if index + 1 < len(parts):
                return parts[index + 1]

    return None


def extract_username(url: str):
    """
    Extract username from a normal profile URL.

    Example:
        https://www.instagram.com/cristiano/
        -> cristiano
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

    if parts[0] in reserved:
        return None

    return parts[0]


def is_reel_url(url: str) -> bool:
    parts = instagram_parts(url)
    return "reel" in parts or "reels" in parts


def is_post_url(url: str) -> bool:
    parts = instagram_parts(url)
    return "p" in parts or "tv" in parts


def is_profile_url(url: str) -> bool:
    """
    True only for a normal Instagram profile URL.
    """

    parts = instagram_parts(url)

    if not parts:
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

    return len(parts) == 1 and parts[0] not in reserved


# ============================================================
# API HELPERS
# ============================================================

def api_headers():
    return {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST,
    }


def api_get(session, endpoint, params=None):
    """
    Perform GET request against the new RapidAPI Instagram API.
    """

    url = f"{BASE_URL}/{endpoint.lstrip('/')}"

    response = session.get(
        url,
        headers=api_headers(),
        params=params or {},
        timeout=120,
    )

    # Give a useful error for RapidAPI proxy errors.
    if response.status_code == 407:
        raise RuntimeError(
            "RapidAPI returned HTTP 407. "
            "The RapidAPI proxy/upstream connection could not be established."
        )

    if response.status_code == 401:
        raise RuntimeError(
            "RapidAPI authentication failed. "
            "Check RAPIDAPI_KEY."
        )

    if response.status_code == 403:
        raise RuntimeError(
            "RapidAPI rejected the request. "
            "Check your subscription and API permissions."
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
            "Instagram API returned an invalid JSON response."
        ) from exc


# ============================================================
# GENERIC JSON HELPERS
# ============================================================

def walk_dicts(value):
    """
    Recursively yield every dictionary inside an arbitrary
    JSON structure.
    """

    if isinstance(value, dict):
        yield value

        for child in value.values():
            yield from walk_dicts(child)

    elif isinstance(value, list):

        for child in value:
            yield from walk_dicts(child)


def first_value(data, keys):
    """
    Search recursively for the first value matching one of
    the supplied keys.
    """

    wanted = {key.lower() for key in keys}

    for obj in walk_dicts(data):

        for key, value in obj.items():

            if key.lower() in wanted and value not in (
                None,
                "",
                [],
                {},
            ):
                return value

    return None


def find_media_items(data):
    """
    Try to locate media/reel/post objects inside different
    response structures used by Instagram scraping APIs.
    """

    candidates = []

    for obj in walk_dicts(data):

        # Common media object identifiers.
        if any(
            key in obj
            for key in (
                "pk",
                "id",
                "code",
                "shortNS = {"jpg", "jpeg", "png", "webp", "gif"}


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def extract_username(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.split("/")[0]


def is_profile_url(url: str) -> bool:
    """
    Return True only for a normal Instagram profile URL.

    Handles both:
      /username/
      /username/reel/SHORTCODE/
      /reels/SHORTCODE/
      /p/SHORTCODE/
    """
    parts = [part.lower() for part in urlparse(url).path.strip("/").split("/") if part]

    if not parts:
        return False

    content_segments = {
        "p",
        "reel",
        "reels",
        "tv",
        "stories",
        "explore",
    }

    # A URL such as /username/reel/ABC is a Reel, not a profile.
    if any(part in content_segments for part in parts):
        return False

    return True


def is_reel_url(url: str) -> bool:
    parts = [part.lower() for part in urlparse(url).path.strip("/").split("/") if part]
    return "reel" in parts or "reels" in parts


def is_post_url(url: str) -> bool:
    parts = [part.lower() for part in urlparse(url).path.strip("/").split("/") if part]
    return "p" in parts or "tv" in parts


def extension_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    if "." not in path:
        return ""
    return path.rsplit(".", 1)[-1]


def get_media_extension(media: dict) -> str:
    extension = str(media.get("extension") or "").lower().lstrip(".")

    if extension in VIDEO_EXTENSIONS or extension in IMAGE_EXTENSIONS:
        return extension

    media_url = media.get("url") or ""
    url_extension = extension_from_url(media_url)

    if url_extension in VIDEO_EXTENSIONS or url_extension in IMAGE_EXTENSIONS:
        return url_extension

    return ""


def choose_media_url(urls):
    """
    RapidAPI can return several URLs for the same media item.
    Prefer an actual video URL over a thumbnail/image URL.
    """
    if not isinstance(urls, list):
        return None, None

    candidates = [
        media for media in urls
        if isinstance(media, dict) and media.get("url")
    ]

    # First preference: actual video.
    for media in candidates:
        extension = get_media_extension(media)
        if extension in VIDEO_EXTENSIONS:
            return media.get("url"), extension

    # Second preference: image.
    for media in candidates:
        extension = get_media_extension(media)
        if extension in IMAGE_EXTENSIONS:
            return media.get("url"), extension

    # Last resort: let the server-provided extension decide.
    if candidates:
        media = candidates[0]
        extension = get_media_extension(media) or "bin"
        return media.get("url"), extension

    return None, None


def download_file(session, media_url, filename):
    response = session.get(
        media_url,
        stream=True,
        timeout=300,
    )
    response.raise_for_status()

    with open(filename, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)


def download_with_ytdlp(url: str, temp_dir: str, username: str):
    """
    Fallback downloader for Reels/videos when RapidAPI only returns
    Instagram's JPG thumbnail.

    Requires:
        pip install -U yt-dlp

    yt-dlp currently has a dedicated Instagram extractor and supports
    /reel/ and /reels/ URLs.
    """
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError(
            "yt-dlp is required for Instagram video fallback. "
            "Install it with: pip install -U yt-dlp"
        ) from exc

    safe_username = sanitize_filename(username or "instagram")

    output_template = os.path.join(
        temp_dir,
        f"{safe_username}_%(autonumber)02d.%(ext)s",
    )

    ydl_opts = {
        # Prefer a progressive MP4 when Instagram exposes one.
        "format": "best[ext=mp4]/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "socket_timeout": 60,
        "retries": 3,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        downloaded_files = []

        requested = info.get("requested_downloads") or []
        for item in requested:
            filepath = item.get("filepath")
            if filepath and os.path.isfile(filepath):
                downloaded_files.append(filepath)

        if not downloaded_files:
            prepared = ydl.prepare_filename(info)
            if os.path.isfile(prepared):
                downloaded_files.append(prepared)

            # yt-dlp may choose a different extension after post-processing.
            base, _ = os.path.splitext(prepared)
            for filename in os.listdir(temp_dir):
                full_path = os.path.join(temp_dir, filename)
                if (
                    os.path.isfile(full_path)
                    and os.path.splitext(filename)[0] == os.path.basename(base)
                ):
                    downloaded_files.append(full_path)

        # Remove duplicates while preserving order.
        unique_files = []
        seen = set()

        for filepath in downloaded_files:
            real_path = os.path.abspath(filepath)
            if real_path not in seen and os.path.isfile(real_path):
                seen.add(real_path)
                unique_files.append(real_path)

        if not unique_files:
            raise Exception("yt-dlp did not produce a downloadable video.")

        return unique_files


def download_instagram(url: str):
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": API_HOST,
        "Content-Type": "application/json",
    }

    session = requests.Session()
    temp_dir = tempfile.mkdtemp()
    filenames = []

    try:
        # ---------------- PROFILE ---------------- #
        if is_profile_url(url):
            username = extract_username(url)

            response = session.post(
                PROFILE_API_URL,
                json={"username": username},
                headers=headers,
                timeout=120,
            )
            response.raise_for_status()

            result = response.json().get("result", {})

            media_url = (
                result.get("profile_pic_url_hd")
                or result.get("profile_pic_url")
            )

            if not media_url:
                raise Exception("Profile picture not found.")

            username = sanitize_filename(
                result.get("username", username)
            )

            filename = os.path.join(
                temp_dir,
                f"{username}_profile.jpg",
            )

            download_file(session, media_url, filename)
            filenames.append(filename)

            return filenames

        # ---------------- REELS / POSTS ---------------- #
        response = session.post(
            MEDIA_API_URL,
            json={"url": url},
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()

        data = response.json()

        if not data:
            raise Exception("No media found.")

        # API responses from this endpoint have changed over time.
        # Some Reel responses now contain only image_versions2/JPG
        # thumbnails even though the media is a video.
        first_item = data[0] if isinstance(data, list) else {}
        username = sanitize_filename(
            first_item.get("meta", {}).get("username", "instagram")
            if isinstance(first_item, dict)
            else "instagram"
        )

        for index, item in enumerate(data):
            if not isinstance(item, dict):
                continue

            media_url, extension = choose_media_url(item.get("urls", []))

            if not media_url:
                continue

            filename = os.path.join(
                temp_dir,
                f"{username}_{index + 1}.{extension}",
            )

            download_file(session, media_url, filename)
            filenames.append(filename)

        # -------------------------------------------------
        # IMPORTANT:
        # If this is a Reel and RapidAPI returned only a JPG
        # thumbnail, do NOT send that JPG. Use yt-dlp instead.
        # -------------------------------------------------
        has_video = any(
            os.path.splitext(filename)[1].lower().lstrip(".")
            in VIDEO_EXTENSIONS
            for filename in filenames
        )

        if is_reel_url(url) and not has_video:
            # Remove thumbnail files before fallback.
            for filename in filenames:
                try:
                    os.remove(filename)
                except OSError:
                    pass

            filenames.clear()

            return download_with_ytdlp(
                url=url,
                temp_dir=temp_dir,
                username=username,
            )

        if not filenames:
            # For video posts where RapidAPI gives no usable media,
            # try yt-dlp as a fallback.
            if is_reel_url(url) or is_post_url(url):
                return download_with_ytdlp(
                    url=url,
                    temp_dir=temp_dir,
                    username=username,
                )

            raise Exception("No downloadable media found.")

        return filenames

    finally:
        session.close()
