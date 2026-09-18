import os
import re
import shutil
import tempfile
from urllib.parse import urlparse

import requests


# ============================================================
# CONFIGURATION
# ============================================================

# ------------------------------------------------------------
# PRIMARY RAPIDAPI
# ------------------------------------------------------------

PRIMARY_API_KEY = os.getenv("RAPIDAPI_KEY")
PRIMARY_API_HOST = os.getenv(
    "RAPIDAPI_HOST",
    "instagram-scraper2.p.rapidapi.com",
)

# ------------------------------------------------------------
# BACKUP RAPIDAPI - INSTAGRAM LOOTER
# ------------------------------------------------------------

BACKUP_API_KEY = os.getenv("RAPIDAPI_BACKUP_KEY")
BACKUP_API_HOST = os.getenv(
    "RAPIDAPI_BACKUP_HOST",
    "instagram-looter2.p.rapidapi.com",
)


# ------------------------------------------------------------
# Media extensions
# ------------------------------------------------------------

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
# CUSTOM EXCEPTION
# ============================================================

class APIError(RuntimeError):
    pass


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
# GENERIC JSON WALKER
# ============================================================

def walk(value):
    """
    Recursively walk dictionaries/lists.
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
    Find first non-empty value matching one of the keys.
    """

    wanted = {
        key.lower()
        for key in keys
    }

    for obj in walk(data):

        if not isinstance(obj, dict):
            continue

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
# API REQUEST
# ============================================================

def api_get(
    session,
    host,
    key,
    endpoint,
    params=None,
    timeout=120,
):
    """
    Generic RapidAPI GET request.
    """

    if not key:
        raise APIError(
            f"RapidAPI key is not configured for {host}."
        )

    url = (
        f"https://{host}/"
        f"{endpoint.lstrip('/')}"
    )

    headers = {
        "x-rapidapi-key": key,
        "x-rapidapi-host": host,
        "accept": "application/json",
    }

    try:

        response = session.get(
            url,
            headers=headers,
            params=params or {},
            timeout=timeout,
        )

    except requests.RequestException as exc:

        raise APIError(
            f"Request failed for {host}: {exc}"
        ) from exc

    if response.status_code == 401:

        raise APIError(
            f"{host}: HTTP 401 - authentication failed."
        )

    if response.status_code == 403:

        raise APIError(
            f"{host}: HTTP 403 - request rejected."
        )

    if response.status_code == 404:

        raise APIError(
            f"{host}: HTTP 404 - endpoint/content not found."
        )

    if response.status_code == 407:

        raise APIError(
            f"{host}: HTTP 407 - provider/proxy connection failed."
        )

    if response.status_code == 429:

        raise APIError(
            f"{host}: HTTP 429 - rate limit exceeded."
        )

    if not response.ok:

        raise APIError(
            f"{host}: HTTP {response.status_code}."
        )

    try:

        return response.json()

    except ValueError as exc:

        raise APIError(
            f"{host}: API returned invalid JSON."
        ) from exc


# ============================================================
# PRIMARY API
# ============================================================

def primary_get_media_info(
    session,
    shortcode,
):
    """
    Existing primary API.

    Endpoint:
        /media_info_v2

    Parameter:
        short_code
    """

    if not shortcode:
        raise APIError(
            "Instagram shortcode is missing."
        )

    return api_get(
        session,
        PRIMARY_API_HOST,
        PRIMARY_API_KEY,
        "/media_info_v2",
        {
            "short_code": shortcode,
        },
    )


def primary_get_profile(
    session,
    username,
):
    """
    Existing primary profile API.

    Endpoint:
        /user_info

    Parameter:
        user_name
    """

    return api_get(
        session,
        PRIMARY_API_HOST,
        PRIMARY_API_KEY,
        "/user_info",
        {
            "user_name": username,
        },
    )


# ============================================================
# BACKUP API - INSTAGRAM LOOTER
# ============================================================

def backup_get_download_link(
    session,
    instagram_url,
):
    """
    Instagram Looter backup.

    First:
        GET /post-dl?url=<instagram_url>

    If that doesn't return a usable URL:
        GET /post?url=<instagram_url>
    """

    errors = []

    # --------------------------------------------------------
    # 1. Direct download endpoint
    # --------------------------------------------------------

    try:

        data = api_get(
            session,
            BACKUP_API_HOST,
            BACKUP_API_KEY,
            "/post-dl",
            {
                "url": instagram_url,
            },
        )

        media_url = extract_media_url(
            data
        )

        if media_url:

            return data, media_url

        errors.append(
            "post-dl returned no usable media URL"
        )

    except Exception as exc:

        errors.append(
            f"post-dl: {exc}"
        )

    # --------------------------------------------------------
    # 2. Media information endpoint
    # --------------------------------------------------------

    try:

        data = api_get(
            session,
            BACKUP_API_HOST,
            BACKUP_API_KEY,
            "/post",
            {
                "url": instagram_url,
            },
        )

        media_url = extract_media_url(
            data
        )

        if media_url:

            return data, media_url

        errors.append(
            "post returned no usable media URL"
        )

    except Exception as exc:

        errors.append(
            f"post: {exc}"
        )

    raise APIError(
        "Instagram Looter failed: "
        + " | ".join(errors)
    )


def backup_get_profile(
    session,
    username,
):
    """
    Instagram Looter profile fallback.

    Endpoint:
        /profile2

    Parameter:
        username
    """

    return api_get(
        session,
        BACKUP_API_HOST,
        BACKUP_API_KEY,
        "/profile2",
        {
            "username": username,
        },
    )


# ============================================================
# MEDIA URL EXTRACTION
# ============================================================

def is_http_url(value):
    return (
        isinstance(value, str)
        and value.startswith(
            (
                "http://",
                "https://",
            )
        )
    )


def extract_media_url(data):
    """
    Extract a media/download URL from the various
    possible Instagram Looter response structures.
    """

    if not data:
        return None

    # --------------------------------------------------------
    # Most likely direct download fields
    # --------------------------------------------------------

    direct_keys = (
        "download_url",
        "download_link",
        "media_url",
        "video_url",
        "image_url",
        "file_url",
        "url",
        "src",
        "play_url",
        "playable_url",
        "direct_url",
        "video",
        "image",
    )

    # --------------------------------------------------------
    # First pass:
    # Prefer explicit download/media fields.
    # --------------------------------------------------------

    for obj in walk(data):

        if not isinstance(obj, dict):
            continue

        for key in direct_keys:

            value = obj.get(key)

            if is_http_url(value):

                # Don't accidentally return the
                # original Instagram page URL.
                if "instagram.com" in value.lower():

                    path = urlparse(value).path.lower()

                    if (
                        "/p/" in path
                        or "/reel/" in path
                        or "/reels/" in path
                        or "/tv/" in path
                    ):
                        continue

                return value

    # --------------------------------------------------------
    # video_versions
    # --------------------------------------------------------

    for obj in walk(data):

        if not isinstance(obj, dict):
            continue

        for key in (
            "video_versions",
            "video_versions2",
            "videos",
        ):

            versions = obj.get(key)

            if not isinstance(
                versions,
                list,
            ):
                continue

            candidates = []

            for item in versions:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                value = (
                    item.get("url")
                    or item.get("src")
                    or item.get("video_url")
                )

                if not is_http_url(value):
                    continue

                width = item.get(
                    "width"
                ) or 0

                height = item.get(
                    "height"
                ) or 0

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
                        value,
                    )
                )

            if candidates:

                candidates.sort(
                    key=lambda x: x[0],
                    reverse=True,
                )

                return candidates[0][1]

    # --------------------------------------------------------
    # image_versions2
    # --------------------------------------------------------

    for obj in walk(data):

        if not isinstance(obj, dict):
            continue

        versions = obj.get(
            "image_versions2"
        )

        if not isinstance(
            versions,
            dict,
        ):
            continue

        candidates = versions.get(
            "candidates"
        )

        if not isinstance(
            candidates,
            list,
        ):
            continue

        best = None
        best_area = -1

        for item in candidates:

            if not isinstance(
                item,
                dict,
            ):
                continue

            value = item.get(
                "url"
            )

            if not is_http_url(value):
                continue

            width = item.get(
                "width"
            ) or 0

            height = item.get(
                "height"
            ) or 0

            try:

                area = (
                    int(width)
                    * int(height)
                )

            except Exception:

                area = 0

            if area > best_area:

                best_area = area
                best = value

        if best:
            return best

    # --------------------------------------------------------
    # display_resources
    # --------------------------------------------------------

    for obj in walk(data):

        if not isinstance(obj, dict):
            continue

        resources = obj.get(
            "display_resources"
        )

        if not isinstance(
            resources,
            list,
        ):
            continue

        candidates = []

        for item in resources:

            if not isinstance(
                item,
                dict,
            ):
                continue

            value = (
                item.get("src")
                or item.get("url")
            )

            if not is_http_url(value):
                continue

            width = item.get(
                "config_width"
            ) or 0

            height = item.get(
                "config_height"
            ) or 0

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
                    value,
                )
            )

        if candidates:

            candidates.sort(
                key=lambda x: x[0],
                reverse=True,
            )

            return candidates[0][1]

    return None


# ============================================================
# PRIMARY RESPONSE MEDIA OBJECT
# ============================================================

def best_video_url(obj):
    if not isinstance(obj, dict):
        return None

    for key in (
        "video_url",
        "video_url_hd",
        "video_url_standard",
        "play_url",
        "download_url",
        "video",
    ):

        value = obj.get(key)

        if is_http_url(value):
            return value

    for key in (
        "video_versions",
        "video_versions2",
        "videos",
    ):

        versions = obj.get(key)

        if not isinstance(
            versions,
            list,
        ):
            continue

        candidates = []

        for item in versions:

            if not isinstance(
                item,
                dict,
            ):
                continue

            value = (
                item.get("url")
                or item.get("src")
                or item.get("video_url")
            )

            if not is_http_url(value):
                continue

            width = item.get(
                "width"
            ) or 0

            height = item.get(
                "height"
            ) or 0

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
                    value,
                )
            )

        if candidates:

            candidates.sort(
                key=lambda x: x[0],
                reverse=True,
            )

            return candidates[0][1]

    return None


def best_image_url(obj):
    if not isinstance(obj, dict):
        return None

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

        if is_http_url(value):
            return value

    versions = obj.get(
        "image_versions2"
    )

    if isinstance(
        versions,
        dict,
    ):

        candidates = versions.get(
            "candidates"
        )

        if isinstance(
            candidates,
            list,
        ):

            best = None
            best_area = -1

            for item in candidates:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                value = item.get(
                    "url"
                )

                if not is_http_url(value):
                    continue

                width = item.get(
                    "width"
                ) or 0

                height = item.get(
                    "height"
                ) or 0

                try:

                    area = (
                        int(width)
                        * int(height)
                    )

                except Exception:

                    area = 0

                if area > best_area:

                    best_area = area
                    best = value

            if best:
                return best

    return None


def find_media_object(
    data,
    shortcode=None,
):
    """
    Find media object in primary API response.
    """

    if shortcode:

        target = shortcode.lower()

        for obj in walk(data):

            if not isinstance(
                obj,
                dict,
            ):
                continue

            for key in (
                "code",
                "shortcode",
                "short_code",
                "media_code",
            ):

                value = obj.get(key)

                if (
                    value is not None
                    and str(value).lower()
                    == target
                ):
                    return obj

    candidates = []

    for obj in walk(data):

        if not isinstance(
            obj,
            dict,
        ):
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
# CAROUSEL
# ============================================================

def get_carousel_items(media):
    if not isinstance(
        media,
        dict,
    ):
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

        if isinstance(
            value,
            list,
        ):
            return value

        if isinstance(
            value,
            dict,
        ):

            edges = value.get(
                "edges"
            )

            if isinstance(
                edges,
                list,
            ):

                items = []

                for edge in edges:

                    if not isinstance(
                        edge,
                        dict,
                    ):
                        continue

                    node = edge.get(
                        "node"
                    )

                    if isinstance(
                        node,
                        dict,
                    ):
                        items.append(node)

                if items:
                    return items

    return []


# ============================================================
# DOWNLOAD REMOTE FILE
# ============================================================

def download_file(
    session,
    url,
    filename=None,
):
    """
    Download remote media.

    If filename is not provided, determine extension
    from Content-Type / URL.
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

    content_type = (
        response.headers.get(
            "content-type",
            ""
        ).lower()
    )

    if filename is None:

        if "video" in content_type:

            extension = ".mp4"

        elif "png" in content_type:

            extension = ".png"

        elif "webp" in content_type:

            extension = ".webp"

        elif "gif" in content_type:

            extension = ".gif"

        else:

            extension = ".jpg"

        filename = tempfile.mktemp(
            suffix=extension
        )

    with open(
        filename,
        "wb",
    ) as file:

        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):

            if chunk:
                file.write(chunk)

    return filename


# ============================================================
# DOWNLOAD MEDIA FROM PRIMARY API
# ============================================================

def download_primary_media(
    session,
    url,
    temp_dir,
):
    """
    Download using the current primary API.
    """

    shortcode = extract_shortcode(url)

    if not shortcode:
        raise APIError(
            "Could not extract Instagram shortcode."
        )

    data = primary_get_media_info(
        session,
        shortcode,
    )

    media = find_media_object(
        data,
        shortcode,
    )

    if media is None:

        raise APIError(
            "Primary API returned no media object."
        )

    # --------------------------------------------------------
    # Carousel
    # --------------------------------------------------------

    carousel = get_carousel_items(
        media
    )

    if carousel:

        files = []

        for index, item in enumerate(
            carousel,
            start=1,
        ):

            video = best_video_url(
                item
            )

            image = best_image_url(
                item
            )

            media_url = (
                video
                or image
            )

            if not media_url:
                continue

            extension = (
                ".mp4"
                if video
                else ".jpg"
            )

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

    # --------------------------------------------------------
    # Single media
    # --------------------------------------------------------

    video = best_video_url(
        media
    )

    image = best_image_url(
        media
    )

    media_url = (
        video
        or image
    )

    if not media_url:

        raise APIError(
            "Primary API returned no downloadable media URL."
        )

    extension = (
        ".mp4"
        if video
        else ".jpg"
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
# DOWNLOAD MEDIA FROM BACKUP API
# ============================================================

def download_backup_media(
    session,
    url,
    temp_dir,
):
    """
    Instagram Looter fallback.

    Priority:

        /post-dl
            ↓
        /post
    """

    data, media_url = (
        backup_get_download_link(
            session,
            url,
        )
    )

    # --------------------------------------------------------
    # Download direct media URL
    # --------------------------------------------------------

    shortcode = (
        extract_shortcode(url)
        or "instagram"
    )

    # We don't force .mp4/.jpg here.
    # Content-Type determines it.
    temp_file = os.path.join(
        temp_dir,
        f"{shortcode}_backup",
    )

    downloaded = download_file(
        session,
        media_url,
        temp_file,
    )

    # --------------------------------------------------------
    # Rename according to actual content type
    # --------------------------------------------------------

    content_type = ""

    try:

        response = session.head(
            media_url,
            timeout=30,
            allow_redirects=True,
        )

        content_type = (
            response.headers.get(
                "content-type",
                ""
            ).lower()
        )

    except Exception:
        pass

    if not os.path.splitext(
        downloaded
    )[1]:

        if "video" in content_type:

            new_path = downloaded + ".mp4"

        elif "png" in content_type:

            new_path = downloaded + ".png"

        elif "webp" in content_type:

            new_path = downloaded + ".webp"

        elif "gif" in content_type:

            new_path = downloaded + ".gif"

        else:

            new_path = downloaded + ".jpg"

        os.rename(
            downloaded,
            new_path,
        )

        downloaded = new_path

    return [downloaded]


# ============================================================
# PROFILE - PRIMARY
# ============================================================

def download_primary_profile(
    session,
    url,
    temp_dir,
):
    username = extract_username(url)

    if not username:
        raise APIError(
            "Invalid Instagram profile URL."
        )

    data = primary_get_profile(
        session,
        username,
    )

    image_url = first_value(
        data,
        (
            "profile_pic_url_hd",
            "hd_profile_pic_url",
            "profile_pic_url",
        ),
    )

    if not is_http_url(
        image_url
    ):

        image_url = best_image_url(
            data
        )

    if not image_url:

        raise APIError(
            "Primary API returned no profile picture."
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
# PROFILE - BACKUP
# ============================================================

def download_backup_profile(
    session,
    url,
    temp_dir,
):
    username = extract_username(url)

    if not username:
        raise APIError(
            "Invalid Instagram profile URL."
        )

    data = backup_get_profile(
        session,
        username,
    )

    image_url = first_value(
        data,
        (
            "profile_pic_url_hd",
            "hd_profile_pic_url",
            "profile_pic_url",
            "profile_pic",
            "image_url",
            "profile_picture",
        ),
    )

    if not is_http_url(
        image_url
    ):

        image_url = best_image_url(
            data
        )

    if not image_url:

        raise APIError(
            "Instagram Looter returned no profile picture."
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
# YT-DLP FINAL FALLBACK
# ============================================================

def download_with_ytdlp(
    url,
    temp_dir,
):
    """
    Final fallback after both RapidAPI providers fail.
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
# MAIN DOWNLOAD FUNCTION
# ============================================================

def download_instagram(url):
    """
    Main entry point used by messages.py.

    Download order:

        PROFILE:
            Primary API
                ↓
            Instagram Looter
                ↓
            error

        MEDIA:
            Primary API
                ↓
            Instagram Looter /post-dl
                ↓
            Instagram Looter /post
                ↓
            yt-dlp
                ↓
            error
    """

    if not isinstance(
        url,
        str,
    ):
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

    primary_error = None
    backup_error = None

    try:

        # ====================================================
        # PROFILE
        # ====================================================

        if is_profile_url(url):

            # ------------------------------------------------
            # PRIMARY
            # ------------------------------------------------

            try:

                return download_primary_profile(
                    session,
                    url,
                    temp_dir,
                )

            except Exception as exc:

                primary_error = exc

            # ------------------------------------------------
            # BACKUP
            # ------------------------------------------------

            try:

                return download_backup_profile(
                    session,
                    url,
                    temp_dir,
                )

            except Exception as exc:

                backup_error = exc

            raise RuntimeError(
                "Profile download failed. "
                f"Primary API: {primary_error}. "
                f"Backup API: {backup_error}."
            )

        # ====================================================
        # MEDIA
        # ====================================================

        # ----------------------------------------------------
        # 1. PRIMARY API
        # ----------------------------------------------------

        try:

            return download_primary_media(
                session,
                url,
                temp_dir,
            )

        except Exception as exc:

            primary_error = exc

        # ----------------------------------------------------
        # 2. INSTAGRAM LOOTER BACKUP
        # ----------------------------------------------------

        try:

            return download_backup_media(
                session,
                url,
                temp_dir,
            )

        except Exception as exc:

            backup_error = exc

        # ----------------------------------------------------
        # 3. FINAL YT-DLP FALLBACK
        # ----------------------------------------------------

        try:

            return download_with_ytdlp(
                url,
                temp_dir,
            )

        except Exception as ytdlp_error:

            raise RuntimeError(
                "All Instagram download methods failed.\n\n"
                f"Primary API: {primary_error}\n"
                f"Backup API: {backup_error}\n"
                f"yt-dlp: {ytdlp_error}"
            ) from primary_error

    except Exception:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True,
        )

        raise

    finally:

        session.close()