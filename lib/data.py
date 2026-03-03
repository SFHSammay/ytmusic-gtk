from pydantic import TypeAdapter
from pydantic import BaseModel, Field
from typing import Literal, Optional


class AccountInfo(BaseModel):
    # Field aliases map the JSON key to your Python variable
    account_name: str = Field(alias="accountName")
    channel_handle: str = Field(alias="channelHandle")
    account_photo_url: str = Field(alias="accountPhotoUrl")


class Artist(BaseModel):
    name: str
    id: Optional[str] = None


class Thumbnail(BaseModel):
    url: str
    width: Optional[int] = None
    height: Optional[int] = None


class Album(BaseModel):
    name: str
    id: str


class PodcastInfo(BaseModel):
    id: str
    name: str


class BaseMedia(BaseModel):
    title: str
    video_id: Optional[str] = Field(None, alias="videoId")
    browse_id: Optional[str] = Field(None, alias="browseId")
    artists: Optional[list[Artist]] = None
    thumbnails: Optional[list[Thumbnail]] = None


class Song(BaseMedia):
    duration: str
    played: str


class Track(BaseMedia):
    length: str
    like_status: Optional[Literal["INDIFFERENT", "LIKE", "DISLIKE"]] = Field(
        None, alias="likeStatus"
    )
    video_type: Optional[str] = Field(None, alias="videoType")
    in_library: Optional[bool] = Field(None, alias="inLibrary")
    album: Optional[Album] = None
    year: Optional[str] = None
    thumbnails: Optional[list[Thumbnail]] = Field(None, alias="thumbnail")


class History(BaseModel):
    songs: list[Song]


class WatchPlaylist(BaseModel):
    tracks: list[Track]
    lyrics: Optional[str] = None
    playlist_id: Optional[str] = Field(None, alias="playlistId")
    related: Optional[str] = None


Songs = TypeAdapter(list[Song])


class ThumbnailContainer(BaseModel):
    thumbnails: list[Thumbnail]


class VideoDetails(BaseModel):
    video_id: str = Field(alias="videoId")
    title: str
    length_seconds: str = Field(alias="lengthSeconds")
    channel_id: str = Field(alias="channelId")
    author: str
    thumbnail: ThumbnailContainer
    music_video_type: Optional[str] = Field(None, alias="musicVideoType")
    view_count: Optional[str] = Field(None, alias="viewCount")


class MicroformatDataRenderer(BaseModel):
    url_canonical: str = Field(alias="urlCanonical")
    title: str
    description: str
    thumbnail: ThumbnailContainer


class Microformat(BaseModel):
    microformat_data_renderer: MicroformatDataRenderer = Field(
        alias="microformatDataRenderer"
    )


class SongDetail(BaseModel):
    video_details: VideoDetails = Field(alias="videoDetails")
    microformat: Microformat


def test():
    import logging

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Add lib to sys.path
    import sys
    import os
    import pathlib

    sys.path.append(str(pathlib.Path(__file__).parent.parent))

    from lib.net.client import auto_login

    yt = auto_login()
    if not yt:
        logger.error("Failed to login")
        return

    logger.info("Testing parsing of History...")
    try:
        history_data = yt.get_history()
        songs = Songs.validate_python(history_data)
        logger.info(f"Successfully parsed {len(songs)} songs from history.")

        if songs and songs[0].video_id:
            video_id = songs[0].video_id

            logger.info(f"Testing parsing of SongDetail for video_id {video_id}...")
            song_data = yt.get_song(video_id)
            song_detail = SongDetail.model_validate(song_data)
            logger.info(
                f"Successfully parsed song detail: {song_detail.video_details.title}"
            )

            logger.info(f"Testing parsing of WatchPlaylist for video_id {video_id}...")
            playlist_data = yt.get_watch_playlist(videoId=video_id)
            watch_playlist = WatchPlaylist.model_validate(playlist_data)
            logger.info(
                f"Successfully parsed watch playlist with {len(watch_playlist.tracks)} tracks."
            )

    except Exception as e:
        logger.error(f"Failed to parse: {e}")
        raise


if __name__ == "__main__":
    test()
