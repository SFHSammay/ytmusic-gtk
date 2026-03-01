from pydantic import TypeAdapter
from pydantic import BaseModel, Field
from typing import List, Optional


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
    artists: Optional[List[Artist]] = None
    thumbnails: Optional[List[Thumbnail]] = None


class Song(BaseMedia):
    duration: str
    played: str


class History(BaseModel):
    songs: List[Song]


Songs = TypeAdapter(List[Song])
