from typing import Any
from typing import cast
from lib.sys.env import CACHE_DIR
from typing import Literal
from lib.data import SongDetail
from lib.data import Playlist
from reactivex import combine_latest
import pathlib
import enum
import logging
import pathlib
from dataclasses import dataclass, field, replace
from typing import Optional

from gi.repository import GLib, Gst
from reactivex.subject import BehaviorSubject, Subject
from reactivex import operators as ops
import reactivex as rx
import ytmusicapi


# Enum for the player state
class PlayState(enum.Enum):
    EMPTY = 0
    PLAYING = 1
    PAUSED = 2
    LOADING = 3


LikeStatus = Literal["INDIFFERENT", "LIKE", "DISLIKE"]


@dataclass
class MediaStatus:
    id: str
    # URL of the song
    url: Optional[str] = field(default=None)
    audio_file: BehaviorSubject[Optional[pathlib.Path]] = field(
        default_factory=lambda: BehaviorSubject[Optional[pathlib.Path]](None)
    )

    title: Optional[str] = field(default=None)
    artist: Optional[str] = field(default=None)
    album_name: Optional[str] = field(default=None)
    year: Optional[str] = field(default=None)
    album_art: Optional[str] = field(default=None)
    like_status: BehaviorSubject[LikeStatus] = field(
        default_factory=lambda: BehaviorSubject[LikeStatus]("INDIFFERENT")
    )


@dataclass
class StreamStatus:
    current_time: BehaviorSubject[int] = field(
        default_factory=lambda: BehaviorSubject(0)
    )

    total_time: BehaviorSubject[int] = field(default_factory=lambda: BehaviorSubject(0))
    volume: BehaviorSubject[float] = field(default_factory=lambda: BehaviorSubject(1.0))
    seek_request: Subject[int] = field(default_factory=Subject)


@dataclass
class CurrentPlaylist:
    media: BehaviorSubject[list[MediaStatus]] = field(
        default_factory=lambda: BehaviorSubject([])
    )
    index: BehaviorSubject[int] = field(default_factory=lambda: BehaviorSubject(0))
    name: BehaviorSubject[Optional[str]] = field(
        default_factory=lambda: BehaviorSubject[Optional[str]](None)
    )


@dataclass
class PlayerState:
    """Holds all reactive state and playing logic for the app."""

    state: BehaviorSubject[PlayState] = field(
        default_factory=lambda: BehaviorSubject(PlayState.EMPTY)
    )

    stream: StreamStatus = field(default_factory=StreamStatus)

    # Actions & System
    # volume: BehaviorSubject[float] = field(default_factory=lambda: BehaviorSubject(1.0))
    shuffle_on: BehaviorSubject[bool] = field(
        default_factory=lambda: BehaviorSubject(False)
    )
    repeat_on: BehaviorSubject[bool] = field(
        default_factory=lambda: BehaviorSubject(False)
    )

    playlist: CurrentPlaylist = field(default_factory=CurrentPlaylist)

    @property
    def current(self) -> "rx.Observable[Optional[MediaStatus]]":
        return combine_latest(self.playlist.media, self.playlist.index).pipe(
            ops.map(lambda x: x[0][x[1]] if 0 <= x[1] < len(x[0]) else None),
            ops.distinct_until_changed(),
        )

    @property
    def current_item(self) -> Optional[MediaStatus]:
        media_list = self.playlist.media.value
        idx = self.playlist.index.value
        if 0 <= idx < len(media_list):
            return media_list[idx]
        return None


INFO_CACHE = {}


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


def play_audio(
    state: PlayerState,
    yt: "ytmusicapi.YTMusic",
    video_id: Optional[str] = None,
    playlist_id: Optional[str] = None,
    initial_temp_music: Optional[MediaStatus] = None,
) -> None:
    import threading

    state.state.on_next(PlayState.LOADING)
    if initial_temp_music:
        state.playlist.media.on_next([initial_temp_music])
        state.playlist.index.on_next(0)

    def fetch_details() -> None:
        try:
            raw_playlist = None

            if playlist_id and not playlist_id.startswith("RD"):
                logging.info(f"Fetching playlist details for {playlist_id}")
                raw_playlist = yt.get_playlist(playlist_id)
            elif video_id:
                logging.info(f"Fetching song details for {video_id}")
                raw_playlist = yt.get_watch_playlist(video_id)
            if not raw_playlist:
                logging.warning("No additional details found for this item.")
                return

            playlist = Playlist.model_validate(raw_playlist)

            media_list = []
            # Try to fetch song details in a playlist
            for track in playlist.tracks:
                id = track.video_id
                if not id:
                    continue
                logging.debug(f"Fetching song details for {id}")
                # detail = get_item_info(yt, id)
                status = MediaStatus(
                    id=id,
                    # url=track.url,
                    title=track.title,
                    # artist=detail.video_details.author,
                    album_name=track.album.name if track.album else None,
                    year=track.year,
                    album_art=track.thumbnails[-1].url if track.thumbnails else None,
                    like_status=(
                        BehaviorSubject[LikeStatus](track.like_status)
                        if track.like_status
                        else BehaviorSubject[LikeStatus]("INDIFFERENT")
                    ),
                )
                media_list.append(status)

            first_song = media_list[0]
            audio_file = get_audio_file(yt, first_song.id)
            logging.info(f"Audio file: {audio_file}")

            first_song.audio_file.on_next(audio_file)
            # Update media list
            state.playlist.media.on_next(media_list)
            state.playlist.index.on_next(0)

            state.state.on_next(PlayState.PLAYING)

        except Exception as e:
            logging.error(f"Could not fetch or download media: {e}")

    threading.Thread(target=fetch_details, daemon=True).start()


def setup_player(state: PlayerState) -> Gst.Element:
    """
    Initializes the GStreamer player and MPRIS controller, binding them to
    the given PlayerState via functional reactive streams.
    """
    from lib.sys.mpris import setup_mpris_controller

    if not Gst.is_initialized():
        Gst.init(None)

    import typing

    player = typing.cast(Gst.Element, Gst.ElementFactory.make("playbin", "player"))
    if not player:
        logging.error("Failed to create GStreamer playbin element.")
        raise RuntimeError("GStreamer initialization failed")

    flags = player.get_property("flags")
    # Disable video output since this is an audio player
    flags &= ~(1 << 0)
    player.set_property("flags", flags)

    def on_audio_file_changed(file_path: pathlib.Path | None) -> None:
        if file_path:
            player.set_state(Gst.State.READY)
            player.set_property("uri", file_path.as_uri())
            if state.state.value == PlayState.PLAYING:
                player.set_state(Gst.State.PLAYING)
        else:
            player.set_state(Gst.State.NULL)

    import reactivex as rx

    state.current.pipe(
        ops.map(lambda s: s.audio_file if s else rx.just(None)),
        ops.switch_latest(),
        ops.distinct_until_changed(),
    ).subscribe(on_audio_file_changed)

    def on_state_changed(s: PlayState) -> None:
        has_audio = state.current_item and state.current_item.audio_file.value
        if not has_audio:
            if s == PlayState.EMPTY:
                player.set_state(Gst.State.NULL)
                state.playlist.media.on_next([])
                state.playlist.index.on_next(0)
            return

        if s == PlayState.PLAYING:
            player.set_state(Gst.State.PLAYING)
        elif s == PlayState.PAUSED or s == PlayState.LOADING:
            player.set_state(Gst.State.PAUSED)
            if s == PlayState.LOADING and state.current_item:
                # Reset time to 0 when loading new track
                state.stream.current_time.on_next(0)

        elif s == PlayState.EMPTY:
            player.set_state(Gst.State.NULL)
            state.playlist.media.on_next([])
            state.playlist.index.on_next(0)

    state.state.subscribe(on_state_changed)

    def on_volume_changed(vol: float) -> None:
        player.set_property("volume", vol)

    state.stream.volume.subscribe(on_volume_changed)

    def update_time_state() -> bool:
        # Only update time if we're currently playing, to avoid unnecessary queries when paused
        if not state.current_item:
            return True  # Keep timeout alive
        if state.state.value == PlayState.PLAYING:
            # Query position
            success_pos, pos = player.query_position(Gst.Format.TIME)
            if success_pos:
                state.stream.current_time.on_next(pos)

            # Query total duration
            success_dur, dur = player.query_duration(Gst.Format.TIME)
            if success_dur:
                state.stream.total_time.on_next(dur)
        return True  # Keep timeout alive

    GLib.timeout_add(500, update_time_state)

    bus = player.get_bus()
    if not bus:
        logging.error("Failed to get GStreamer bus.")
        raise RuntimeError("GStreamer bus initialization failed")
    bus.add_signal_watch()

    def on_bus_message(bus: Gst.Bus, message: Gst.Message) -> None:
        # If current is None, we have no track loaded, so ignore messages
        if not state.current_item:
            return
        if message.type == Gst.MessageType.EOS:
            state.state.on_next(PlayState.PAUSED)
            # state.current_time.on_next(0)
            state.stream.current_time.on_next(0)
            player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, 0)
        elif message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logging.error(f"GStreamer Error: {err}, {debug}")
            state.state.on_next(PlayState.PAUSED)

    bus.connect("message", on_bus_message)

    def on_seek_request(position_ns: int) -> None:
        if not state.current_item:
            return
        player.seek_simple(
            Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, position_ns
        )
        state.stream.current_time.on_next(position_ns)

    def on_current(current: Optional[MediaStatus]) -> None:
        if not current:
            return
        state.stream.seek_request.subscribe(on_seek_request)

    # state.seek_request.subscribe(on_seek_request)
    state.current.subscribe(on_current)

    setup_mpris_controller(state)

    return player
