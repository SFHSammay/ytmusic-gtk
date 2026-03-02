import enum
from dataclasses import dataclass, field
from reactivex.subject import BehaviorSubject
from typing import Optional
import pathlib


class PlayItem:
    id: str
    title: str
    artist: str
    album_name: str
    year: str
    album_art: str
    current_time: int
    total_time: int
    volume: float
    is_liked: bool
    is_disliked: bool
    shuffle_on: bool
    repeat_on: bool
    audio_file: Optional[pathlib.Path]
    show_now_playing: bool


# Enum for the player state
class PlayState(enum.Enum):
    EMPTY = 0
    PLAYING = 1
    PAUSED = 2
    LOADING = 3


@dataclass
class PlayerState:
    """Holds all reactive state for the PlayBar."""

    state: BehaviorSubject[PlayState] = field(
        default_factory=lambda: BehaviorSubject(PlayState.EMPTY)
    )

    id: BehaviorSubject[Optional[str]] = field(
        default_factory=lambda: BehaviorSubject[Optional[str]](None)
    )

    # Track Info
    title: BehaviorSubject[str] = field(
        default_factory=lambda: BehaviorSubject(
            "Nothing is playing. Click a song to get started!"
        )
    )
    artist: BehaviorSubject[str] = field(default_factory=lambda: BehaviorSubject(""))
    album_name: BehaviorSubject[str] = field(
        default_factory=lambda: BehaviorSubject("")
    )
    year: BehaviorSubject[str] = field(default_factory=lambda: BehaviorSubject(""))
    album_art: BehaviorSubject[str] = field(
        default_factory=lambda: BehaviorSubject("audio-x-generic-symbolic")
    )

    # Timing (Changed to integers for nanoseconds)
    current_time: BehaviorSubject[int] = field(
        default_factory=lambda: BehaviorSubject(0)
    )
    total_time: BehaviorSubject[int] = field(default_factory=lambda: BehaviorSubject(0))

    # Actions & System
    volume: BehaviorSubject[float] = field(default_factory=lambda: BehaviorSubject(1.0))
    is_liked: BehaviorSubject[bool] = field(
        default_factory=lambda: BehaviorSubject(False)
    )
    is_disliked: BehaviorSubject[bool] = field(
        default_factory=lambda: BehaviorSubject(False)
    )
    shuffle_on: BehaviorSubject[bool] = field(
        default_factory=lambda: BehaviorSubject(False)
    )
    repeat_on: BehaviorSubject[bool] = field(
        default_factory=lambda: BehaviorSubject(False)
    )

    audio_file: BehaviorSubject[Optional[pathlib.Path]] = field(
        default_factory=lambda: BehaviorSubject[Optional[pathlib.Path]](None)
    )
    # Just a place holder for now.
    show_now_playing: BehaviorSubject[bool] = field(
        default_factory=lambda: BehaviorSubject(False)
    )
