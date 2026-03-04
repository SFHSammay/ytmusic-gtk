from lib.ui.home import HomeSectionData
from pydantic import TypeAdapter
from lib.ui.home import HomePageType
import pathlib
from ytmusicapi.type_alias import JsonDict
from lib.data import WatchPlaylist
from typing import Any
import multiprocessing
from functools import wraps
from typing import Optional, Callable, TypeVar, ParamSpec, cast

import ytmusicapi
import reactivex as rx
from reactivex import operators, Observable
from reactivex.scheduler import ThreadPoolScheduler
from pydantic import BaseModel

from lib.data import AlbumData, AccountInfo, SongDetail

thread_pool_scheduler = ThreadPoolScheduler(max_workers=multiprocessing.cpu_count())

# 1. Bind T to BaseModel (as discussed)
T = TypeVar("T", bound=BaseModel)

# 2. Define P to capture the arguments of the decorated function
P = ParamSpec("P")


def rx_fetch(
    model_class: type[T],
) -> Callable[[Callable[P, Any]], Callable[P, Observable[Optional[tuple[T, dict]]]]]:

    def decorator(
        func: Callable[P, Any],
    ) -> Callable[P, Observable[Optional[tuple[T, dict]]]]:
        @wraps(func)
        def wrapper(
            *args: P.args, **kwargs: P.kwargs
        ) -> Observable[Optional[tuple[T, dict]]]:
            # Extract blocking safely
            blocking = cast(bool, kwargs.pop("blocking", False))

            def fetch_work() -> Optional[tuple[T, dict]]:
                raw_dict = func(*args, **kwargs)
                if not raw_dict:
                    return None
                return (model_class.model_validate(raw_dict), raw_dict)

            observable = rx.from_callable(fetch_work)

            if blocking:
                return observable

            return observable.pipe(
                operators.subscribe_on(thread_pool_scheduler),
                operators.start_with(cast(Optional[tuple[T, dict]], None)),
            )

        return wrapper

    return decorator


class YTClient:
    def __init__(self, yt: ytmusicapi.YTMusic):
        self.yt = yt

    # 4. Add `*, blocking: bool = False` back to the signatures so your IDE knows it exists
    @rx_fetch(SongDetail)
    def get_song(
        self,
        video_id: str,
        signature_timestamp: Optional[int] = None,
        *,
        blocking: bool = False,
    ) -> Optional[dict]:
        return self.yt.get_song(video_id, signature_timestamp)

    @rx_fetch(AccountInfo)
    def get_account_info(self, *, blocking: bool = False) -> Optional[dict]:
        return self.yt.get_account_info()

    @rx_fetch(AlbumData)
    def get_playlist(
        self,
        playlist_id: str,
        limit: int = 100,
        related: bool = False,
        suggestions_limit: int = 0,
        *,
        blocking: bool = False,
    ) -> Optional[dict]:
        return self.yt.get_playlist(playlist_id, limit, related, suggestions_limit)

    @rx_fetch(WatchPlaylist)
    def get_watch_playlist(
        self,
        video_id: Optional[str] = None,
        playlist_id: Optional[str] = None,
        limit: int = 100,
        radio: bool = False,
        shuffle: bool = False,
        *,
        blocking: bool = False,
    ) -> Optional[dict]:
        return self.yt.get_watch_playlist(video_id, playlist_id, limit, radio, shuffle)

    @rx_fetch(LocalAudio)
    def get_audio_file(self, video_id: str, *, blocking: bool = False) -> LocalAudio:
        from lib.state.player_state import get_audio_file

        path = get_audio_file(self.yt, video_id)
        return LocalAudio(path=path)

    @rx_fetch(HomePageTypeAdapter)
    def get_home(self, limit: int = 100, *, blocking: bool = False) -> Optional[dict]:
        return self.yt.get_home(limit=limit)


class LocalAudio(BaseModel):
    path: pathlib.Path


# Get type of HomePage for type hinting
HomePageType = list[HomeSectionData]
