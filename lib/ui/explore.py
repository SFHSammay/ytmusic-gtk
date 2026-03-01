from utils import load_thumbnail
from reactivex.subject import BehaviorSubject
import ytmusicapi
import threading
import logging
import logging
from lib.data import PodcastInfo
from lib.data import Album
from lib.data import BaseMedia
from lib.types import YTMusicSubject
from gi.repository import Gtk, Adw, GLib
from pydantic import BaseModel, Field
from typing import List, Optional


class NewVideo(BaseMedia):
    playlist_id: Optional[str] = Field(None, alias="playlistId")
    views: Optional[str] = None


class TrendingItem(BaseMedia):
    video_type: Optional[str] = Field(None, alias="videoType")
    is_explicit: Optional[bool] = Field(None, alias="isExplicit")
    playlist_id: Optional[str] = Field(None, alias="playlistId")
    album: Optional[Album] = None
    podcast: Optional[PodcastInfo] = None
    views: Optional[str] = None
    date: Optional[str] = None


class TopEpisode(BaseMedia):
    description: str
    duration: str
    video_type: str = Field(alias="videoType")
    date: str
    podcast: PodcastInfo


class NewRelease(BaseMedia):
    type: str  # e.g., "Album", "Single"
    audio_playlist_id: Optional[str] = Field(None, alias="audioPlaylistId")
    is_explicit: bool = Field(alias="isExplicit")


class Trending(BaseModel):
    playlist: str
    items: List[TrendingItem]


class MoodAndGenre(BaseModel):
    title: str
    params: str


class ExploreData(BaseModel):
    new_releases: List[NewRelease]
    moods_and_genres: List[MoodAndGenre]
    top_episodes: List[TopEpisode]
    trending: Trending
    new_videos: List[NewVideo]


def ExplorePage(
    yt_subject: YTMusicSubject,
) -> Gtk.ScrolledWindow:
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

    explore_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=32)
    explore_box.set_margin_top(24)
    explore_box.set_margin_bottom(24)
    scrolled.set_child(explore_box)

    explore_data_subject = BehaviorSubject[ExploreData | None](None)

    def on_yt_changed(yt: Optional[ytmusicapi.YTMusic]):
        if not yt:
            logging.warning("YT instance is None, cannot fetch explore data.")
            return
        logging.info("YT instance updated, fetching explore data...")

        def fetch_explore(yt: ytmusicapi.YTMusic):
            try:
                raw_explore = yt.get_explore()
                explore_data = ExploreData.model_validate(raw_explore)
                explore_data_subject.on_next(explore_data)

            except Exception as e:
                logging.error(f"Error fetching explore data: {e}")

        threading.Thread(target=fetch_explore, args=(yt,), daemon=True).start()

    yt_subject.subscribe(on_yt_changed)

    def on_data_changed(explore_data: Optional[ExploreData]):
        if not explore_data:
            logging.warning("Explore data is None, cannot update UI.")
            return
        logging.info("Explore data updated, refreshing UI...")
        # Clear existing content
        while True:
            child = explore_box.get_first_child()
            if not child:
                break
            explore_box.remove(child)

        # Populate with new data
        # Each section will be in its own row with a header
        new_releases_header = Gtk.Label(label="New Releases")

        new_releases_header.set_xalign(0)
        new_releases_header.set_margin_start(12)
        new_releases_header.add_css_class("section-header")
        explore_box.append(new_releases_header)

        new_release_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        for new_release in explore_data.new_releases:
            release_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            image = Gtk.Picture()
            load_thumbnail(image, new_release.thumbnails)
            title_label = Gtk.Label(label=new_release.title)
            title_label.set_xalign(0)
            release_widget.append(image)
            release_widget.append(title_label)
            new_release_box.append(release_widget)
        # explore_box.append(new_release_box)
        new_release_scrolled = Gtk.ScrolledWindow()
        new_release_scrolled.set_child(new_release_box)
        new_release_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        # Set height request to show only one row of releases
        new_release_scrolled.set_size_request(-1, 200)
        explore_box.append(new_release_scrolled)

    explore_data_subject.subscribe(on_data_changed)
    return scrolled
