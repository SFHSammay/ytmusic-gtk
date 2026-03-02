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
