import yt_dlp,tempfile,os
def download_instagram(url):
    d=tempfile.mkdtemp()
    out=os.path.join(d,"%(title).80s.%(ext)s")
    opts={"outtmpl":out,"format":"best","quiet":True,"noplaylist":True,
          "merge_output_format":"mp4","retries":3}
    with yt_dlp.YoutubeDL(opts) as y:
        info=y.extract_info(url,download=True)
        return y.prepare_filename(info)
