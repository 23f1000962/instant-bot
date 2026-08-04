import os
import re
import tempfile
from urllib.parse import urlparse

import requests

RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]

MEDIA_API_URL = "https://instagram120.p.rapidapi.com/api/instagram/links"
PROFILE_API_URL = "https://instagram120.p.rapidapi.com/api/instagram/profile"
API_HOST = "instagram120.p.rapidapi.com"


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def extract_username(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.split("/")[0]


def is_profile_url(url: str) -> bool:
    path = urlparse(url).path.strip("/")
    parts = path.split("/")

    if not parts or parts[0] == "":
        return False

    return parts[0] not in (
        "p",
        "reel",
        "tv",
        "stories",
        "explore",
    )


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
                json={
                    "username": username
                },
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
                f"{username}_profile.jpg"
            )

            download_file(session, media_url, filename)

            filenames.append(filename)

            return filenames

        # ---------------- POSTS / REELS ---------------- #

        response = session.post(
            MEDIA_API_URL,
            json={
                "url": url
            },
            headers=headers,
            timeout=120,
        )

        response.raise_for_status()

        data = response.json()

        if not data:
            raise Exception("No media found.")

        username = sanitize_filename(
            data[0].get("meta", {}).get("username", "instagram")
        )

        for index, item in enumerate(data):

            urls = item.get("urls", [])

            if not urls:
                continue

            media = urls[0]

            media_url = media.get("url")

            if not media_url:
                continue

            extension = media.get(
                "extension",
                "mp4"
            ).lower()

            filename = os.path.join(
                temp_dir,
                f"{username}_{index + 1}.{extension}"
            )

            download_file(session, media_url, filename)

            filenames.append(filename)

        if not filenames:
            raise Exception("No downloadable media found.")

        return filenames

    finally:
        session.close()
