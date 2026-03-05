import sys
import threading
from lib.data import SongDetail
import logging
from lib.data import AlbumData
from lib.net.client import LocalAudio
from lib.data import LikeStatus
from lib.net.client import YTClient
from typing import Any
from lib.data import WatchPlaylist
from reactivex import combine_latest
import pathlib
import enum
import logging
import pathlib
from dataclasses import dataclass, field, replace
from typing import Optional

from gi.repository import GLib, Gst, GstApp
from reactivex.subject import BehaviorSubject, Subject
from reactivex import operators as ops
import reactivex as rx
import mpv


# Enum for the player state
class PlayState(enum.Enum):
    EMPTY = 0
    PLAYING = 1
    PAUSED = 2
    LOADING = 3


class RepeatMode(enum.Enum):
    OFF = 0
    ALL = 1
    ONE = 2


@dataclass
class MediaStatus:
    id: str
    # URL of the song
    url: Optional[str] = field(default=None)
    audio_file: BehaviorSubject[Optional[pathlib.Path]] = field(
        default_factory=lambda: BehaviorSubject[Optional[pathlib.Path]](None)
    )
    is_placeholder_music: bool = field(default=False)

    title: Optional[str] = field(default=None)
    artist: Optional[str] = field(default=None)
    album_name: Optional[str] = field(default=None)
    year: Optional[str] = field(default=None)
    album_art: Optional[str] = field(default=None)
    like_status: BehaviorSubject[LikeStatus] = field(
        default_factory=lambda: BehaviorSubject[LikeStatus]("INDIFFERENT")
    )
    bytes: BehaviorSubject[Optional[bytes]] = field(
        default_factory=lambda: BehaviorSubject[Optional[bytes]](None)
    )

    song: Optional[SongDetail] = field(default=None)


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
    playlist_id: BehaviorSubject[Optional[str]] = field(
        default_factory=lambda: BehaviorSubject[Optional[str]](None)
    )
    index: BehaviorSubject[int] = field(default_factory=lambda: BehaviorSubject(0))
    name: BehaviorSubject[Optional[str]] = field(
        default_factory=lambda: BehaviorSubject[Optional[str]](None)
    )


@dataclass
class PlayerState:
    """Holds all reactive state and playing logic for the app."""

    client: YTClient
    state: BehaviorSubject[PlayState] = field(
        default_factory=lambda: BehaviorSubject(PlayState.EMPTY)
    )

    stream: StreamStatus = field(default_factory=StreamStatus)

    # Actions & System
    # volume: BehaviorSubject[float] = field(default_factory=lambda: BehaviorSubject(1.0))
    shuffle_on: BehaviorSubject[bool] = field(
        default_factory=lambda: BehaviorSubject(False)
    )
    repeat_mode: BehaviorSubject[RepeatMode] = field(
        default_factory=lambda: BehaviorSubject(RepeatMode.OFF)
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


def play_watch_playlist(
    state: PlayerState,
    video_id: Optional[str] = None,
    playlist_id: Optional[str] = None,
    placeholder_music: Optional[MediaStatus] = None,
    playlist_title: Optional[str] = None,
) -> None:
    client = state.client

    # If there is no video_id nor playlist_id, we can't play anything
    if not video_id and not playlist_id:
        logging.warning("No video_id nor playlist_id provided.")
        return
    logging.info(f"Playing song with playlist: {playlist_id} {video_id}")

    state.state.on_next(PlayState.LOADING)
    if placeholder_music:
        logging.info("Playing placeholder music")
        placeholder_music.is_placeholder_music = True
        state.playlist.media.on_next([placeholder_music])
        state.playlist.index.on_next(0)
        state.playlist.playlist_id.on_next(playlist_id)
        state.playlist.name.on_next(playlist_title)
    else:
        state.playlist.media.on_next([])
        state.playlist.index.on_next(0)
        state.playlist.playlist_id.on_next(playlist_id)
        state.playlist.name.on_next(playlist_title)

    playlist = client.get_watch_playlist(playlist_id=playlist_id, video_id=video_id)
    # try to get playlist title
    if playlist_id:

        def on_playlist(data: Optional[tuple[AlbumData, dict]]):
            if data is None:
                return
            logging.info("Got playlist title")
            album_data, _ = data
            state.playlist.name.on_next(album_data.title)
            state.playlist.playlist_id.on_next(playlist_id)

        client.get_playlist(playlist_id).subscribe(
            on_next=on_playlist,
            on_error=lambda e: logging.error(f"Could not get playlist title: {e}"),
        )

    def on_playlist(data: Optional[tuple[WatchPlaylist, dict]]):
        if data is None:
            return
        watch_playlist, _ = data

        media_list: list[MediaStatus] = []
        for track in watch_playlist.tracks:
            id = track.video_id
            if not id:
                continue
            media_list.append(
                MediaStatus(
                    id=id,
                    title=track.title,
                    artist=track.artists[0].name if track.artists else None,
                    album_name=track.album.name if track.album else None,
                    year=track.year,
                    album_art=track.thumbnails[-1].url if track.thumbnails else None,
                    like_status=(
                        BehaviorSubject[LikeStatus](track.like_status)
                        if track.like_status
                        else BehaviorSubject[LikeStatus]("INDIFFERENT")
                    ),
                )
            )
        state.playlist.media.on_next(media_list)
        state.playlist.index.on_next(0)
        state.playlist.playlist_id.on_next(watch_playlist.playlist_id)

    playlist.subscribe(
        on_next=on_playlist,
        on_error=lambda e: logging.error(f"Could not fetch or download media: {e}"),
    )


def play_next(state: PlayerState) -> None:
    media_list = state.playlist.media.value
    if not media_list:
        return
    idx = state.playlist.index.value
    if state.shuffle_on.value:
        import random

        next_idx = random.randint(0, len(media_list) - 1)
    else:
        next_idx = idx + 1
        if next_idx >= len(media_list):
            if state.repeat_mode.value == RepeatMode.ALL:
                next_idx = 0
            else:
                state.state.on_next(PlayState.PAUSED)
                state.stream.current_time.on_next(0)
                return
    state.playlist.index.on_next(next_idx)


def play_previous(state: PlayerState) -> None:
    media_list = state.playlist.media.value
    if not media_list:
        return
    idx = state.playlist.index.value
    if state.shuffle_on.value:
        import random

        next_idx = random.randint(0, len(media_list) - 1)
    else:
        next_idx = idx - 1
        if next_idx < 0:
            if state.repeat_mode.value == RepeatMode.ALL:
                next_idx = len(media_list) - 1
            else:
                next_idx = 0
    state.playlist.index.on_next(next_idx)


def setup_player(state: PlayerState) -> mpv.MPV:
    """
    Initializes the MPV player and binds it to
    the given PlayerState via functional reactive streams.
    """
    import locale

    locale.setlocale(locale.LC_NUMERIC, "C")
    # Initialize MPV for background audio only
    player = mpv.MPV(ytdl=False, video=False)

    def on_audio_file_changed(audio_file_path: pathlib.Path | None) -> None:
        if audio_file_path and audio_file_path.exists():
            player.play(str(audio_file_path))
            if state.state.value == PlayState.PLAYING:
                player.pause = False
            else:
                player.pause = True
        else:
            player.stop()

    # Subscribe to the audio file path instead of raw bytes
    state.current.pipe(
        ops.map(lambda s: s.audio_file if s else rx.just(None)),
        ops.switch_latest(),
        ops.distinct_until_changed(),
    ).subscribe(on_audio_file_changed)

    def on_state_changed(s: PlayState) -> None:
        has_audio = state.current_item and state.current_item.audio_file.value

        if not has_audio:
            if s == PlayState.EMPTY:
                player.stop()
                state.playlist.media.on_next([])
                state.playlist.index.on_next(0)
            return

        if s == PlayState.PLAYING:
            player.pause = False
        elif s == PlayState.PAUSED or s == PlayState.LOADING:
            player.pause = True
            if s == PlayState.LOADING and state.current_item:
                state.stream.current_time.on_next(0)
        elif s == PlayState.EMPTY:
            player.stop()
            state.playlist.media.on_next([])
            state.playlist.index.on_next(0)

    state.state.subscribe(on_state_changed)

    def on_volume_changed(vol: float) -> None:
        # MPV volume is generally 0-100+
        player.volume = vol * 100

    state.stream.volume.subscribe(on_volume_changed)

    def update_time_state() -> bool:
        if not state.current_item:
            return True  # Keep timeout alive

        if state.state.value == PlayState.PLAYING:
            # MPV uses seconds (float), while the app streams expect nanoseconds (int)
            pos = player.time_pos
            if pos is not None:
                state.stream.current_time.on_next(int(pos * 1e9))

            dur = player.duration
            if dur is not None:
                state.stream.total_time.on_next(int(dur * 1e9))

        return True

    GLib.timeout_add(500, update_time_state)

    # Watch for End of File (EOS) via MPV's property observer
    @player.property_observer("eof-reached")
    def on_eof(name, value):
        if value:  # True when the track finishes naturally

            def handle_eos() -> bool:
                if state.repeat_mode.value == RepeatMode.ONE:
                    player.time_pos = 0
                    player.pause = False
                    state.stream.current_time.on_next(0)
                    return False

                play_next(state)
                return False

            GLib.idle_add(handle_eos)

    def on_seek_request(position_ns: int) -> None:
        if not state.current_item:
            return

        # Convert nanoseconds to seconds for MPV
        pos_sec = position_ns / 1e9
        player.time_pos = pos_sec
        state.stream.current_time.on_next(position_ns)

    state.stream.seek_request.subscribe(on_seek_request)

    def on_current(current: Optional[MediaStatus]) -> None:
        logging.info(f"Current: {current}")
        if not current or current.audio_file.value or current.is_placeholder_music:
            return

        client = state.client
        state.state.on_next(PlayState.LOADING)
        current_id = current.id

        if not current_id:
            return

        def on_audio_file(audio_file: Optional[tuple[Any, Any]]) -> None:
            if not current:
                raise RuntimeError("Current item changed during audio file fetch")
            if not audio_file:
                return

            file = audio_file[0].path
            if not file.exists():
                raise RuntimeError(f"Audio file not found: {file}")

            if not state.current_item or not state.current_item.id == current_id:
                logging.warning(
                    "Current item changed during audio file fetch, discarding result"
                )
                return

            # Note: Populating bytes is no longer strictly needed for playback,
            # but kept intact in case your app relies on it elsewhere (e.g. streaming to clients).
            def read_file_bytes(path: pathlib.Path):
                try:
                    if not current:
                        return
                    audio_bytes = path.read_bytes()
                    GLib.idle_add(lambda: current.bytes.on_next(audio_bytes) or False)
                except Exception as e:
                    logging.error(f"Failed to read audio file bytes: {e}")

            current.audio_file.on_next(file)
            threading.Thread(target=read_file_bytes, args=(file,)).start()

            # Trigger play state
            GLib.idle_add(lambda: state.state.on_next(PlayState.PLAYING) or False)

        client.get_audio_file(current_id).subscribe(
            on_next=on_audio_file,
            on_error=lambda e: logging.error(
                f"Could not fetch audio for {current_id}: {e}"
            ),
        )

        def on_song_detail(data: Optional[tuple[Any, Any]]) -> None:
            if not current:
                raise RuntimeError("Current item changed during song detail fetch")
            if not data:
                return
            song_detail, raw_data = data
            if not state.current_item or not state.current_item.id == current_id:
                logging.warning(
                    "Current item changed during song detail fetch, discarding"
                )
                return

            current.song = song_detail

            def delayed_history_add():
                if state.current_item and state.current_item.id == current_id:
                    client.add_history_item(rx.just(song_detail)).subscribe(
                        on_next=lambda _: logging.info(
                            f"Added {current_id} to history"
                        ),
                        on_error=lambda e: logging.error(
                            f"Could not add {current_id} to history: {e}"
                        ),
                    )
                return False

            GLib.timeout_add(10 * 1000, delayed_history_add)

        client.get_song(current_id).subscribe(
            on_next=on_song_detail,
            on_error=lambda e: logging.error(
                f"Could not fetch song detail for {current_id}: {e}"
            ),
        )

    state.current.subscribe(on_current)

    if sys.platform.startswith("linux"):
        from lib.sys.mpris import setup_mpris_controller

        setup_mpris_controller(state)
    elif sys.platform == "darwin":
        from lib.sys.mac_media import setup_mac_media_controller

        setup_mac_media_controller(state)

    return player
