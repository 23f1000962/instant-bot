import os
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

    media_url = data[0]["urls"][0]["url"]

    temp_dir = tempfile.mkdtemp()
    filename = os.path.join(temp_dir, "instagram.mp4")

    media = requests.get(media_url, stream=True)
    media.raise_for_status()

    with open(filename, "wb") as f:
        for chunk in media.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return filename
