import os
import re
import tempfile
import requests

RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]

API_URL = "https://instagram120.p.rapidapi.com/api/instagram/links"
API_HOST = "instagram120.p.rapidapi.com"


def download_instagram(url: str):
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": API_HOST,
        "Content-Type": "application/json",
    }

    payload = {
        "url": url
    }

    session = requests.Session()

    response = session.post(
        API_URL,
        json=payload,
        headers=headers,
        timeout=120
    )

    response.raise_for_status()

    data = response.json()

    if not data:
        raise Exception("No media found.")

    temp_dir = tempfile.mkdtemp()
    filenames = []

    username = data[0].get("meta", {}).get("username", "instagram")
    username = re.sub(r'[\\/*?:"<>|]', "_", username)

    for index, item in enumerate(data):

        urls = item.get("urls", [])

        if not urls:
            continue

        media = urls[0]

        media_url = media.get("url")

        if not media_url:
            continue

        extension = media.get("extension", "mp4").lower()

        filename = os.path.join(
            temp_dir,
            f"{username}_{index + 1}.{extension}"
        )

        media_response = session.get(
            media_url,
            stream=True,
            timeout=300
        )

        media_response.raise_for_status()

        with open(filename, "wb") as f:
            for chunk in media_response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

        filenames.append(filename)

    session.close()

    if not filenames:
        raise Exception("No downloadable media found.")

    return filenames
