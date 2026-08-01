import os
import tempfile
import yt_dlp
import shutil

print("FFmpeg:", shutil.which("ffmpeg"))


def download_instagram(url: str) -> str:
    temp_dir = tempfile.mkdtemp()

    output_template = os.path.join(
        temp_dir,
        "%(title).80s.%(ext)s"
    )

    ydl_opts = {
        "outtmpl": output_template,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": False,
        "verbose": True,
        "noplaylist": True,
        "retries": 5,
        "extractor_retries": 5,
        "socket_timeout": 120,
        "http_chunk_size": 10485760,
        "restrictfilenames": True,
        "nopart": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        print("=" * 80)

        for f in info.get("formats", []):
            print(
                f"id={f.get('format_id')}, "
                f"ext={f.get('ext')}, "
                f"vcodec={f.get('vcodec')}, "
                f"acodec={f.get('acodec')}"
            )

        print("=" * 80)

        raise Exception("Format listing complete")

        # The code below won't execute because of the exception.
        # Keep it only if you remove the exception later.
        filename = ydl.prepare_filename(info)

        if not os.path.exists(filename):
            base, _ = os.path.splitext(filename)
            if os.path.exists(base + ".mp4"):
                filename = base + ".mp4"

        return filename
