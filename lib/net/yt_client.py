from lib.data import HomePageTypeAdapter
from pydantic import TypeAdapter
import pathlib
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

T = TypeVar("T")
P = ParamSpec("P")

type RxVal[V] = V | Observable[V]

V = TypeVar("V")


class LocalAudio(BaseModel):
    path: pathlib.Path


def rx_fetch(
    parser: type[T] | TypeAdapter[T],
) -> Callable[[Callable[..., Any]], Callable[..., Observable[Optional[tuple[T, Any]]]]]:

    adapter = parser if isinstance(parser, TypeAdapter) else TypeAdapter(parser)

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Observable[Optional[tuple[T, Any]]]]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            blocking = cast(bool, kwargs.pop("blocking", False))

            # 1. Check if ANY arguments are Observables
            has_observable = any(isinstance(a, Observable) for a in args) or any(
                isinstance(v, Observable) for v in kwargs.values()
            )

            # 2. Synchronous/Blocking Path (Bypass Rx entirely if no observables are used)
            if blocking:
                if has_observable:
                    raise ValueError(
                        "Cannot use blocking=True when passing Observables as arguments."
                    )

                raw_data = func(*args, **kwargs)
                if not raw_data:
                    return None
                return (adapter.validate_python(raw_data), raw_data)

            # 3. Reactive Path
            # Convert all args and kwargs into Observables (wrap static values in rx.just)
            obs_args = [a if isinstance(a, Observable) else rx.just(a) for a in args]
            kwarg_keys = list(kwargs.keys())
            obs_kwargs = [
                kwargs[k] if isinstance(kwargs[k], Observable) else rx.just(kwargs[k])
                for k in kwarg_keys
            ]

            all_observables = obs_args + obs_kwargs

            # 4. Create the trigger stream
            if all_observables:
                # combine_latest emits a tuple of the latest values whenever ANY of the observables emit
                trigger = rx.combine_latest(*all_observables)
            else:
                # Fallback for methods with 0 arguments (like get_account_info)
                trigger = rx.just(())

            # 5. Define the actual fetch work that runs when trigger emits
            def create_fetch_observable(
                combined_vals: tuple,
            ) -> Observable[Optional[tuple[T, Any]]]:
                # Reconstruct args and kwargs from the combined tuple
                if all_observables:
                    resolved_args = combined_vals[: len(args)]
                    resolved_kwargs = dict(zip(kwarg_keys, combined_vals[len(args) :]))
                else:
                    resolved_args = ()
                    resolved_kwargs = {}

                def fetch_work() -> Optional[tuple[T, Any]]:
                    raw_data = func(*resolved_args, **resolved_kwargs)
                    if not raw_data:
                        return None
                    return (adapter.validate_python(raw_data), raw_data)

                # Wrap the I/O work in a thread pool observable
                return rx.from_callable(fetch_work).pipe(
                    operators.subscribe_on(thread_pool_scheduler)
                )

            # 6. switch_map cancels the previous fetch if a new argument emits before it finishes
            return trigger.pipe(
                operators.switch_map(create_fetch_observable),
                operators.start_with(cast(Optional[tuple[T, Any]], None)),
            )

        return wrapper

    return decorator


def unwrap(val: RxVal[V]) -> V:
    """
    Bypasses static type errors for arguments intercepted by @rx_fetch.
    At runtime, @rx_fetch ensures this is already the raw value (V).
    """
    # Ensure that the value is not an Observable
    if isinstance(val, Observable):
        raise ValueError("unwrap() should only be called on non-Observable values.")
    return val


class YTClient:
    def __init__(self, api: ytmusicapi.YTMusic):
        self.api = api

    # 4. Add `*, blocking: bool = False` back to the signatures so your IDE knows it exists
    @rx_fetch(SongDetail)
    def get_song(
        self,
        video_id: RxVal[str],
        signature_timestamp: RxVal[Optional[int]] = None,
        *,
        blocking: bool = False,
    ) -> Optional[dict]:

        return self.api.get_song(unwrap(video_id), unwrap(signature_timestamp))

    @rx_fetch(AccountInfo)
    def get_account_info(self, *, blocking: bool = False) -> Optional[dict]:
        return self.api.get_account_info()

    @rx_fetch(AlbumData)
    def get_playlist(
        self,
        playlist_id: RxVal[str],
        limit: RxVal[int] = 100,
        related: RxVal[bool] = False,
        suggestions_limit: RxVal[int] = 0,
        *,
        blocking: bool = False,
    ) -> Optional[dict]:
        return self.api.get_playlist(
            unwrap(playlist_id),
            unwrap(limit),
            unwrap(related),
            unwrap(suggestions_limit),
        )

    @rx_fetch(WatchPlaylist)
    def get_watch_playlist(
        self,
        video_id: RxVal[Optional[str]] = None,
        playlist_id: RxVal[Optional[str]] = None,
        limit: RxVal[int] = 100,
        radio: RxVal[bool] = False,
        shuffle: RxVal[bool] = False,
        *,
        blocking: bool = False,
    ) -> Optional[dict]:
        return self.api.get_watch_playlist(
            unwrap(video_id),
            unwrap(playlist_id),
            unwrap(limit),
            unwrap(radio),
            unwrap(shuffle),
        )

    @rx_fetch(LocalAudio)
    def get_audio_file(
        self, video_id: RxVal[str], *, blocking: bool = False
    ) -> Optional[dict]:
        from lib.state.player_state import get_audio_file

        path = get_audio_file(self.api, unwrap(video_id))
        return {
            "path": path,
        }

    @rx_fetch(HomePageTypeAdapter)
    def get_home(
        self, limit: RxVal[int] = 100, *, blocking: bool = False
    ) -> Optional[list]:
        return self.api.get_home(limit=unwrap(limit))

    @rx_fetch(AlbumData)
    def get_album(
        self,
        browse_id: RxVal[str],
        *,
        blocking: bool = False,
    ) -> Optional[dict]:
        return self.api.get_album(unwrap(browse_id))

    @
    def rate_song(self, video_id: str, rating: str) -> None:
        self.api.rate_song(video_id, rating)
