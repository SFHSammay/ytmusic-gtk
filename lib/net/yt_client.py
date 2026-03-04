from lib.data import AlbumData
from lib.data import AccountInfo
from typing import cast
from reactivex import operators
import multiprocessing
import ytmusicapi
import reactivex as rx
from reactivex import Observable
from reactivex.scheduler import ThreadPoolScheduler
from lib.data import SongDetail
from typing import Optional

thread_pool_scheduler = ThreadPoolScheduler(max_workers=multiprocessing.cpu_count())


class YTClient:
    def __init__(self, yt: ytmusicapi.YTMusic):
        self.yt = yt

    def get_song(
        self, video_id: str, signature_timestamp: Optional[int] = None, blocking=False
    ) -> Observable[Optional[tuple[SongDetail, dict]]]:

        # Define the synchronous work as a simple callable
        def fetch_song() -> Optional[tuple[SongDetail, dict]]:
            song_dict = self.yt.get_song(video_id, signature_timestamp)
            song = SongDetail.model_validate(song_dict)
            return (song, song_dict)

        if blocking:
            return rx.from_callable(fetch_song)

        return rx.from_callable(fetch_song).pipe(
            # 1. Offload the fetch to the thread pool
            operators.subscribe_on(thread_pool_scheduler),
            # 2. Immediately emit None to the subscriber before the fetch begins
            operators.start_with(cast(tuple[SongDetail, dict] | None, None)),
        )

    def get_account_info(
        self, blocking=False
    ) -> Observable[Optional[tuple[AccountInfo, dict]]]:
        def fetch_account_info() -> Optional[tuple[AccountInfo, dict]]:
            info_dict = self.yt.get_account_info()
            if not info_dict:
                return None
            account_info = AccountInfo.model_validate(info_dict)
            return (account_info, info_dict)

        if blocking:
            return rx.from_callable(fetch_account_info)

        return rx.from_callable(fetch_account_info).pipe(
            operators.subscribe_on(thread_pool_scheduler),
            operators.start_with(cast(tuple[AccountInfo, dict] | None, None)),
        )

    def get_playlist(
        self,
        playlist_id: str,
        limit: int = 100,
        related: bool = False,
        suggestions_limit: int = 0,
        blocking=False,
    ) -> Observable[Optional[tuple[AlbumData, dict]]]:
        def fetch_playlist() -> Optional[tuple[AlbumData, dict]]:
            playlist_dict = self.yt.get_playlist(
                playlist_id, limit, related, suggestions_limit
            )
            if not playlist_dict:
                return None
            playlist = AlbumData.model_validate(playlist_dict)
            return (playlist, playlist_dict)
        if blocking:
            return rx.from_callable(fetch_playlist)

        return rx.from_callable(fetch_playlist).pipe(
            operators.subscribe_on(thread_pool_scheduler),
            operators.start_with(cast(tuple[AlbumData, dict] | None, None)),
        )
