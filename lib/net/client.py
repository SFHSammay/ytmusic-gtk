from requests import Response
import logging
from reactivex.scheduler.mainloop.gtkscheduler import GtkScheduler
from lib.data import LikeStatus
from lib.data import RateSongResponse
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
import time
from lib.data import AlbumData, AccountInfo, SongDetail

import threading
import sqlite3
import pickle
import hashlib

logger = logging.getLogger(__name__)

thread_pool_scheduler = ThreadPoolScheduler(max_workers=multiprocessing.cpu_count())
download_scheduler = ThreadPoolScheduler(max_workers=1)

T = TypeVar("T")
P = ParamSpec("P")

type RxVal[V] = V | Observable[V]

V = TypeVar("V")


class LocalAudio(BaseModel):
    path: pathlib.Path


class HTTPResponse(BaseModel, arbitrary_types_allowed=True):
    response: Response


def _make_hashable(obj: Any) -> Any:
    """Recursively converts mutable types to immutable types for cache hashing."""
    if isinstance(obj, list):
        return tuple(_make_hashable(e) for e in obj)
    if isinstance(obj, dict):
        return frozenset((k, _make_hashable(v)) for k, v in obj.items())
    return obj


_SQLITE_DB_PATH = "rx_cache.db"
_sqlite_write_lock = threading.Lock()


def _init_sqlite_cache():
    """Initializes the SQLite database with WAL mode for better concurrency."""
    with _sqlite_write_lock:
        with sqlite3.connect(_SQLITE_DB_PATH) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    func_name TEXT,
                    cache_key TEXT,
                    timestamp REAL,
                    data BLOB,
                    PRIMARY KEY (func_name, cache_key)
                )
            """
            )


_init_sqlite_cache()


def rx_fetch(
    parser: type[T] | TypeAdapter[T],
    *,
    scheduler: Optional[ThreadPoolScheduler] = None,
    use_cache: bool = True,
    disk_cache: bool = True,
    ttl: float = 60.0 * 5,
) -> Callable[
    [Callable[P, Any]],
    Callable[P, Observable[Optional[tuple[T, Any]]]],
]:
    adapter = parser if isinstance(parser, TypeAdapter) else TypeAdapter(parser)

    def decorator(
        func: Callable[P, Any],
    ) -> Callable[P, Observable[Optional[tuple[T, Any]]]]:

        cache_store: dict[tuple, tuple[float, Optional[tuple[T, Any]]]] = {}
        func_name = func.__name__

        def _get_disk_key(resolved_args: tuple, resolved_kwargs: dict) -> str:
            """Creates a stable string for hashing, ignoring 'self' to avoid pickling errors."""
            safe_args = (
                resolved_args[1:]
                if resolved_args and hasattr(resolved_args[0], "__dict__")
                else resolved_args
            )
            cache_kwargs = {
                k: v
                for k, v in resolved_kwargs.items()
                if k not in ("blocking", "force_refresh", "cache_only")
            }
            stable_str = (
                f"{func_name}:{repr(safe_args)}:{repr(sorted(cache_kwargs.items()))}"
            )
            return hashlib.sha256(stable_str.encode("utf-8")).hexdigest()

        def _get_cache(
            cache_key: tuple, resolved_args: tuple, resolved_kwargs: dict
        ) -> tuple[bool, Optional[tuple[T, Any]]]:
            # 1. Memory Check
            if use_cache and cache_key in cache_store:
                cached_time, val = cache_store[cache_key]
                if time.time() - cached_time < ttl:
                    return True, val

            # 2. Disk Check
            if disk_cache:
                disk_key = _get_disk_key(resolved_args, resolved_kwargs)
                try:
                    with sqlite3.connect(_SQLITE_DB_PATH, timeout=10) as conn:
                        cursor = conn.execute(
                            "SELECT timestamp, data FROM cache WHERE func_name=? AND cache_key=?",
                            (func_name, disk_key),
                        )
                        row = cursor.fetchone()
                        if row:
                            cached_time, blob = row
                            if time.time() - cached_time < ttl:
                                raw_data = pickle.loads(blob)
                                parsed = (
                                    (adapter.validate_python(raw_data), raw_data)
                                    if raw_data
                                    else None
                                )

                                # Backfill memory cache
                                if use_cache:
                                    cache_store[cache_key] = (time.time(), parsed)
                                return True, parsed
                            else:
                                # Cleanup expired disk entry
                                with _sqlite_write_lock:
                                    with sqlite3.connect(
                                        _SQLITE_DB_PATH, timeout=10
                                    ) as del_conn:
                                        del_conn.execute(
                                            "DELETE FROM cache WHERE func_name=? AND cache_key=?",
                                            (func_name, disk_key),
                                        )
                except Exception as e:
                    logger.warning(f"Disk cache read failed for {func_name}: {e}")

            return False, None

        def _set_cache(
            cache_key: tuple,
            resolved_args: tuple,
            resolved_kwargs: dict,
            raw_data: Any,
            parsed_data: Optional[tuple[T, Any]],
        ):
            current_time = time.time()
            if use_cache:
                cache_store[cache_key] = (current_time, parsed_data)

            if disk_cache:
                disk_key = _get_disk_key(resolved_args, resolved_kwargs)
                try:
                    blob = pickle.dumps(raw_data)
                    with _sqlite_write_lock:
                        with sqlite3.connect(_SQLITE_DB_PATH, timeout=10) as conn:
                            conn.execute(
                                "REPLACE INTO cache (func_name, cache_key, timestamp, data) VALUES (?, ?, ?, ?)",
                                (func_name, disk_key, current_time, blob),
                            )
                except pickle.PicklingError:
                    logger.debug(
                        f"Skipping disk cache for {func_name}: Data is not picklable."
                    )
                except Exception as e:
                    logger.warning(f"Disk cache write failed for {func_name}: {e}")

        @wraps(func)
        def wrapper(
            *args: P.args, **kwargs: P.kwargs
        ) -> Observable[Optional[tuple[T, Any]]]:
            blocking = cast(bool, kwargs.get("blocking", False))
            has_observable = any(isinstance(a, Observable) for a in args) or any(
                isinstance(v, Observable) for v in kwargs.values()
            )

            # --- Synchronous Path ---
            if blocking:
                if has_observable:
                    raise ValueError("Cannot use blocking=True with Observables.")

                force_refresh = cast(bool, kwargs.get("force_refresh", False))
                cache_only = cast(bool, kwargs.get("cache_only", False))

                cache_kwargs = {
                    k: v
                    for k, v in kwargs.items()
                    if k not in ("blocking", "force_refresh", "cache_only")
                }
                cache_key = (
                    tuple(_make_hashable(a) for a in args),
                    frozenset((k, _make_hashable(v)) for k, v in cache_kwargs.items()),
                )

                has_valid_cache, cached_val = False, None
                if not force_refresh:
                    has_valid_cache, cached_val = _get_cache(cache_key, args, kwargs)

                if cache_only and has_valid_cache:
                    return rx.just(cached_val)

                raw_data = func(*args, **kwargs)
                parsed = (
                    (adapter.validate_python(raw_data), raw_data) if raw_data else None
                )

                _set_cache(cache_key, args, kwargs, raw_data, parsed)

                if not cache_only and has_valid_cache:
                    # NEW: Drop duplicate synchronous emissions
                    if cached_val == parsed:
                        return rx.just(cached_val)
                    return rx.of(cached_val, parsed)

                return rx.just(parsed)

            # --- Reactive Path ---
            obs_args = [a if isinstance(a, Observable) else rx.just(a) for a in args]
            kwarg_keys = list(kwargs.keys())
            obs_kwargs = [
                kwargs[k] if isinstance(kwargs[k], Observable) else rx.just(kwargs[k])
                for k in kwarg_keys
            ]

            all_observables = cast(list[Observable[Any]], obs_args + obs_kwargs)

            trigger = (
                cast(Observable[tuple[Any, ...]], rx.combine_latest(*all_observables))
                if all_observables
                else rx.just(())
            )

            def create_fetch_observable(
                combined_vals: tuple,
            ) -> Observable[Optional[tuple[T, Any]]]:
                if all_observables:
                    resolved_args = combined_vals[: len(args)]
                    resolved_kwargs = dict(zip(kwarg_keys, combined_vals[len(args) :]))
                else:
                    resolved_args, resolved_kwargs = (), {}

                force_refresh = cast(bool, resolved_kwargs.get("force_refresh", False))
                cache_only = cast(bool, resolved_kwargs.get("cache_only", False))

                cache_kwargs = {
                    k: v
                    for k, v in resolved_kwargs.items()
                    if k not in ("blocking", "force_refresh", "cache_only")
                }
                cache_key = (
                    tuple(_make_hashable(a) for a in resolved_args),
                    frozenset((k, _make_hashable(v)) for k, v in cache_kwargs.items()),
                )

                def do_fetch() -> Optional[tuple[T, Any]]:
                    raw_data = func(*resolved_args, **resolved_kwargs)  # type: ignore
                    parsed = (
                        (adapter.validate_python(raw_data), raw_data)
                        if raw_data
                        else None
                    )
                    _set_cache(
                        cache_key, resolved_args, resolved_kwargs, raw_data, parsed
                    )
                    return parsed

                if force_refresh:
                    return rx.from_callable(do_fetch).pipe(
                        operators.subscribe_on(scheduler or thread_pool_scheduler)
                    )

                has_valid_cache, cached_val = _get_cache(
                    cache_key, resolved_args, resolved_kwargs
                )

                if cache_only and has_valid_cache:
                    return rx.just(cached_val)

                fetch_obs = rx.from_callable(do_fetch).pipe(
                    operators.subscribe_on(scheduler or thread_pool_scheduler)
                )

                if not cache_only and has_valid_cache:
                    # NEW: concat them, then filter out identical consecutive values
                    return rx.concat(rx.just(cached_val), fetch_obs).pipe(
                        operators.distinct_until_changed()
                    )

                return fetch_obs

            return trigger.pipe(
                operators.switch_map(create_fetch_observable),
                operators.start_with(cast(Optional[tuple[T, Any]], None)),
            )

        return wrapper

    return decorator


def unwrap(val: RxVal[V]) -> V:
    if isinstance(val, Observable):
        raise ValueError("unwrap() should only be called on non-Observable values.")
    return val


class YTClient:
    def __init__(self, api: ytmusicapi.YTMusic):
        self.api = api

    @rx_fetch(SongDetail)
    def get_song(
        self,
        video_id: RxVal[str],
        signature_timestamp: RxVal[Optional[int]] = None,
        *,
        force_refresh: bool = False,
        blocking: bool = False,
        cache_only: bool = False,
    ) -> Optional[dict]:

        raw = self.api.get_song(unwrap(video_id), unwrap(signature_timestamp))
        import json

        with open("debug_song.json", "w") as f:
            json.dump(raw, f)
        return raw

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
        force_refresh: bool = False,
        blocking: bool = False,
        cache_only: bool = False,
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
        force_refresh: bool = False,
        blocking: bool = False,
        cache_only: bool = False,
    ) -> Optional[dict]:
        logging.debug(
            f"Client: Getting watch playlist: {unwrap(video_id)}, {unwrap(playlist_id)}"
        )
        res = self.api.get_watch_playlist(
            unwrap(video_id),
            unwrap(playlist_id),
            unwrap(limit),
            unwrap(radio),
            unwrap(shuffle),
        )
        import json

        with open("watch_playlist.json", "w") as f:
            json.dump(res, f)
        return res

    @rx_fetch(LocalAudio, scheduler=download_scheduler)
    def get_audio_file(
        self,
        video_id: RxVal[str],
        *,
        blocking: bool = False,
        force_refresh: bool = False,
        cache_only: bool = False,
    ) -> Optional[dict]:
        from lib.net.utils import get_audio_file

        path = get_audio_file(self.api, unwrap(video_id))
        return {
            "path": path,
        }

    @rx_fetch(HomePageTypeAdapter)
    def get_home(
        self,
        limit: RxVal[int] = 100,
        *,
        blocking: bool = False,
        force_refresh: bool = False,
        cache_only: bool = False,
    ) -> Optional[list]:
        return self.api.get_home(limit=unwrap(limit))

    @rx_fetch(AlbumData)
    def get_album(
        self,
        browse_id: RxVal[str],
        *,
        blocking: bool = False,
        force_refresh: bool = False,
    ) -> Optional[dict]:
        return self.api.get_album(unwrap(browse_id))

    # Disabled disk caching here since it's an action, not persistent data retrieval
    @rx_fetch(RateSongResponse, use_cache=False, disk_cache=False)
    def rate_song(
        self,
        video_id: RxVal[str],
        rating: RxVal[LikeStatus],
        *,
        blocking: bool = False,
        force_refresh: bool = False,
        cache_only: bool = False,
    ) -> Optional[dict]:
        logging.debug(
            f"Client: Rating song {unwrap(video_id)} as {unwrap(cast(RxVal[LikeStatus], rating))}"
        )
        self.api.rate_song(
            unwrap(video_id),
            ytmusicapi.LikeStatus(unwrap(cast(RxVal[LikeStatus], rating))),
        )

    @rx_fetch(TypeAdapter(list[AlbumData]))
    def get_library_playlists(
        self,
        limit: RxVal[int] = 100,
        *,
        blocking: bool = False,
        force_refresh: bool = False,
        cache_only: bool = False,
    ) -> Optional[list[dict]]:
        res = self.api.get_library_playlists(limit=unwrap(limit))

        return res

    # Disabled disk caching here since HTTP responses cannot be safely pickled
    @rx_fetch(HTTPResponse, use_cache=False, disk_cache=False)
    def add_history_item(
        self,
        song: RxVal[SongDetail],
        *,
        blocking: bool = False,
        force_refresh: bool = False,
    ) -> Optional[dict]:
        res = self.api.add_history_item(unwrap(song).model_dump(by_alias=True))
        return {"response": res}

    @rx_fetch(TypeAdapter(list[Any]))
    def search(
        self,
        query: RxVal[str],
        filter: RxVal[Optional[str]] = None,
        scope: RxVal[Optional[str]] = None,
        limit: RxVal[int] = 20,
        ignore_spelling: RxVal[bool] = False,
        *,
        blocking: bool = False,
        force_refresh: bool = False,
        cache_only: bool = False,
    ) -> Optional[list[dict]]:
        res = self.api.search(
            unwrap(query),
            unwrap(filter),
            unwrap(scope),
            unwrap(limit),
            unwrap(ignore_spelling),
        )
        import json

        with open("debug_search.json", "w") as f:
            json.dump(res, f)
        return res
