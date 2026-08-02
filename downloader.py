import os
import re
import tempfile
import requests

RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]

API_URL = "https://instagram120.p.rapidapi.com/api/instagram/links"
API_HOST = "instagram120.p.rapidapi.com"


def download_instagram(url: str) -> str:
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": API_HOST,
        "Content-Type": "application/json"
    }

    payload = {
        "url": url
    }

    response = requests.post(API_URL, json=payload, headers=headers)
    response.raise_for_status()

    data = response.json()

    if not data:
        raise Exception("No media found.")

    media_info = data[0]["urls"][0]

    media_url = media_info["url"]
    extension = media_info.get("extension", "mp4")

    username = data[0]["meta"].get("username", "instagram")

    # Make username safe for filenames
    username = re.sub(r'[\\/*?:"<>|]', "_", username)

    temp_dir = tempfile.mkdtemp()

    filename = os.path.join(
        temp_dir,
        f"{username}.{extension}"
    )

    media = requests.get(media_url, stream=True)
    media.raise_for_status()

    with open(filename, "wb") as f:
        for chunk in media.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return filename
