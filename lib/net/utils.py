from lib.data import SongDetail
from lib.sys.env import CACHE_DIR
from typing import Any
from typing import cast
import ytmusicapi
import pathlib
import logging


INFO_CACHE: dict[str, SongDetail] = {}


def get_item_info(yt: "ytmusicapi.YTMusic", video_id: str) -> SongDetail:
    if video_id in INFO_CACHE:
        return INFO_CACHE[video_id]
    data = yt.get_song(video_id)
    song_detail = SongDetail.model_validate(data)
    INFO_CACHE[video_id] = song_detail
    return song_detail


def get_audio_file(yt: "ytmusicapi.YTMusic", video_id: str) -> pathlib.Path:
    from yt_dlp import YoutubeDL

    download_dir = CACHE_DIR / "songs" / video_id
    download_dir.mkdir(parents=True, exist_ok=True)

    logging.info(f"Downloading media to: {download_dir}")

    detail = get_item_info(yt, video_id)
    url = detail.microformat.microformat_data_renderer.url_canonical

    marker_file = download_dir / "downloaded.txt"

    if not marker_file.exists():
        with YoutubeDL(
            params=cast(
                Any,
                {
                    "js_runtimes": {"bun": {}, "node": {}},
                    "paths": {"home": str(download_dir.absolute())},
                    "format": "bestaudio/best",
                    "noplaylist": True,
                    "quiet": True,
                    "no_warnings": True,
                    "outtmpl": {
                        "default": "%(id)s.%(ext)s",
                    },
                },
            )
        ) as ydl:
            ydl.download([url])
        with open(marker_file, "w") as f:
            f.write("downloaded")

    audio_files = list(download_dir.glob("*.m4a"))
    if not audio_files:
        audio_files = list(download_dir.glob("*.webm"))
    if not audio_files:
        audio_files = list(download_dir.glob("*.opus"))
    if not audio_files:
        audio_files = list(download_dir.glob("*.mp3"))
    if not audio_files:
        raise FileNotFoundError(f"No audio files found in {download_dir}")
    return audio_files[0]
