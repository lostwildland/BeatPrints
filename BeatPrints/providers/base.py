"""
Base protocols for BeatPrints metadata providers.
"""

from typing import List, Protocol

from BeatPrints.metadata import AlbumMetadata, TrackMetadata


class MetadataProvider(Protocol):
    """
    Common interface used by the CLI for track and album metadata lookup.
    """

    def get_track(self, query: str, limit: int = 6) -> List[TrackMetadata]:
        ...

    def get_album(
        self, query: str, limit: int = 6, shuffle: bool = False
    ) -> List[AlbumMetadata]:
        ...
