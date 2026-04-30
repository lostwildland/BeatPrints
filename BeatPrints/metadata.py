"""
Provider-neutral metadata models for BeatPrints posters.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TrackMetadata:
    """
    Data structure to store metadata for a track.
    """

    name: str
    artist: str
    album: str
    released: str
    duration: str
    image: str
    label: str
    id: str
    source: str = ""
    source_id: str = ""
    external_url: str = ""
    spotify_id: Optional[str] = None
    spotify_uri: Optional[str] = None


@dataclass
class AlbumMetadata:
    """
    Data structure to store metadata for an album, including a track list.
    """

    name: str
    artist: str
    released: str
    image: str
    label: str
    id: str
    tracks: List[str]
    source: str = ""
    source_id: str = ""
    external_url: str = ""
    spotify_id: Optional[str] = None
    spotify_uri: Optional[str] = None
