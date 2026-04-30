"""
iTunes Search API metadata provider.
"""

import datetime
import random
import re
from html import unescape
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

import requests

from BeatPrints.errors import (
    InvalidSearchLimit,
    NoMatchingAlbumFound,
    NoMatchingTrackFound,
)
from BeatPrints.metadata import AlbumMetadata, TrackMetadata


class ITunesProvider:
    """
    Credential-free provider backed by Apple's iTunes Search API.
    """

    SEARCH_URL = "https://itunes.apple.com/search"
    LOOKUP_URL = "https://itunes.apple.com/lookup"

    def __init__(self, country: str = "US") -> None:
        self.country = country

    def get_track(self, query: str, limit: int = 6) -> List[TrackMetadata]:
        """
        Searches for tracks based on a query, iTunes/Apple Music URL, or Spotify URL.
        """
        if limit < 1:
            raise InvalidSearchLimit

        try:
            track_id = self._itunes_track_id(query)
            if track_id:
                return [self._lookup_track(track_id)]

            search_query, spotify_uri, spotify_id = self._query_from_spotify_url(query)
            results = self._search(search_query, "song", limit)
            tracks = [
                self._track_metadata(item) for item in results if self._is_song(item)
            ]

            if spotify_uri:
                for track in tracks:
                    track.spotify_uri = spotify_uri
                    track.spotify_id = spotify_id

            if not tracks:
                raise NoMatchingTrackFound

            return tracks

        except (KeyError, requests.RequestException, ValueError):
            raise NoMatchingTrackFound

    def get_album(
        self, query: str, limit: int = 6, shuffle: bool = False
    ) -> List[AlbumMetadata]:
        """
        Searches for albums based on a query, iTunes/Apple Music URL, or Spotify URL.
        """
        if limit < 1:
            raise InvalidSearchLimit

        try:
            collection_id = self._itunes_collection_id(query)
            if collection_id:
                return [self._lookup_album(collection_id, shuffle)]

            search_query, spotify_uri, spotify_id = self._query_from_spotify_url(query)
            results = self._search(search_query, "album", limit)
            albums = [
                self._lookup_album(str(item["collectionId"]), shuffle)
                for item in results
                if item.get("wrapperType") == "collection"
            ]

            if spotify_uri:
                for album in albums:
                    album.spotify_uri = spotify_uri
                    album.spotify_id = spotify_id

            if not albums:
                raise NoMatchingAlbumFound

            return albums

        except (KeyError, requests.RequestException, ValueError):
            raise NoMatchingAlbumFound

    def _search(self, query: str, entity: str, limit: int) -> List[dict]:
        response = requests.get(
            self.SEARCH_URL,
            params={
                "term": query,
                "media": "music",
                "entity": entity,
                "limit": limit,
                "country": self.country,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def _lookup(self, item_id: str, entity: Optional[str] = None) -> List[dict]:
        params = {"id": item_id, "country": self.country}
        if entity:
            params["entity"] = entity

        response = requests.get(self.LOOKUP_URL, params=params, timeout=15)
        response.raise_for_status()
        return response.json().get("results", [])

    def _lookup_track(self, track_id: str) -> TrackMetadata:
        for item in self._lookup(track_id):
            if self._is_song(item):
                return self._track_metadata(item)
        raise NoMatchingTrackFound

    def _lookup_album(self, collection_id: str, shuffle: bool = False) -> AlbumMetadata:
        results = self._lookup(collection_id, "song")
        album = next(
            (item for item in results if item.get("wrapperType") == "collection"), None
        )
        songs = [item for item in results if self._is_song(item)]

        if not album:
            raise NoMatchingAlbumFound

        tracks = [
            item["trackName"]
            for item in sorted(songs, key=lambda song: song.get("trackNumber", 0))
        ]

        if shuffle:
            random.shuffle(tracks)

        return self._album_metadata(album, tracks)

    def _track_metadata(self, item: dict) -> TrackMetadata:
        track_id = str(item["trackId"])
        collection_id = str(item.get("collectionId", ""))
        label = self._label_from_copyright(item.get("copyright", ""))
        if not label and collection_id:
            label = self._album_label(collection_id)

        return TrackMetadata(
            name=item["trackName"],
            artist=item["artistName"],
            album=item.get("collectionName", ""),
            released=self._format_released(item.get("releaseDate", "")),
            duration=self._format_duration(item.get("trackTimeMillis", 0)),
            image=self._large_artwork(item.get("artworkUrl100", "")),
            label=label,
            id=track_id,
            source="itunes",
            source_id=track_id,
            external_url=item.get("trackViewUrl")
            or item.get("collectionViewUrl", "")
            or (
                f"https://music.apple.com/album/{collection_id}?i={track_id}"
                if collection_id
                else ""
            ),
        )

    def _album_metadata(self, item: dict, tracks: List[str]) -> AlbumMetadata:
        collection_id = str(item["collectionId"])
        return AlbumMetadata(
            name=item["collectionName"],
            artist=item["artistName"],
            released=self._format_released(item.get("releaseDate", "")),
            image=self._large_artwork(item.get("artworkUrl100", "")),
            label=self._label_from_copyright(item.get("copyright", "")),
            id=collection_id,
            tracks=tracks,
            source="itunes",
            source_id=collection_id,
            external_url=item.get("collectionViewUrl", "")
            or f"https://music.apple.com/album/{collection_id}",
        )

    def _query_from_spotify_url(
        self, query: str
    ) -> tuple[str, Optional[str], Optional[str]]:
        spotify = self._spotify_id_and_type(query)
        if not spotify:
            return query, None, None

        spotify_id, spotify_type = spotify
        spotify_uri = f"spotify:{spotify_type}:{spotify_id}"
        title, artist = self._spotify_page_terms(query)
        search_query = f"{title} {artist}".strip() if artist else title
        return search_query or query, spotify_uri, spotify_id

    def _spotify_id_and_type(self, value: str) -> Optional[tuple[str, str]]:
        cleaned = value.strip().split("?")[0]

        uri = re.fullmatch(r"spotify:(track|album):([0-9A-Za-z]{22})", cleaned)
        if uri:
            return uri.group(2), uri.group(1)

        parsed = urlparse(cleaned)
        match = re.fullmatch(r"/(track|album)/([0-9A-Za-z]{22})", parsed.path)
        if parsed.netloc == "open.spotify.com" and match:
            return match.group(2), match.group(1)

        return None

    def _spotify_page_terms(self, url: str) -> tuple[str, str]:
        response = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        html = response.text

        title = self._meta_title(html)
        artist = self._meta_artist(html)
        return title, artist

    def _meta_title(self, html: str) -> str:
        title = self._first_match(r'<meta property="og:title" content="(.*?)"', html)
        if title:
            return self._clean_spotify_title(title)

        title = self._first_match(r"<title>(.*?)</title>", html)
        if not title:
            return ""
        return self._clean_spotify_title(title)

    def _clean_spotify_title(self, title: str) -> str:
        return unescape(
            re.sub(
                r"\s+-\s+(?:Album|Song|song and lyrics) by .*$",
                "",
                title,
                flags=re.IGNORECASE,
            )
        ).strip()

    def _meta_artist(self, html: str) -> str:
        title = self._first_match(r"<title>(.*?)</title>", html)
        title_match = re.search(
            r"\s+-\s+(?:Album|Song|song and lyrics) by (.*?)\s+\|\s+Spotify",
            title,
            flags=re.IGNORECASE,
        )
        if title_match:
            return unescape(title_match.group(1)).strip()

        desc = self._first_match(
            r'<meta property="og:description" content="(.*?)"', html
        )
        if desc:
            return unescape(desc.split("·")[0]).strip()

        return ""

    def _first_match(self, pattern: str, text: str) -> str:
        match = re.search(pattern, text, flags=re.DOTALL)
        return match.group(1).strip() if match else ""

    def _itunes_track_id(self, query: str) -> Optional[str]:
        parsed = urlparse(query)
        params = parse_qs(parsed.query)
        if parsed.netloc.endswith("apple.com") and params.get("i"):
            return params["i"][0]
        return None

    def _itunes_collection_id(self, query: str) -> Optional[str]:
        parsed = urlparse(query)
        if not parsed.netloc.endswith("apple.com"):
            return None

        ids = re.findall(r"/(\d+)(?:$|[/?])", parsed.path)
        return ids[-1] if ids else None

    def _large_artwork(self, url: str) -> str:
        return re.sub(r"/\d+x\d+bb\.(jpg|png)$", r"/1200x1200bb.\1", url)

    def _format_released(self, value: str) -> str:
        if not value:
            return ""

        date = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.strftime("%B %d, %Y")

    def _format_duration(self, duration_ms: int) -> str:
        minutes = duration_ms // 60000
        seconds = (duration_ms // 1000) % 60
        return f"{minutes:02d}:{seconds:02d}"

    def _label_from_copyright(self, copyright: str) -> str:
        if not copyright:
            return ""

        label = re.sub(r"^[©℗]\s*\d{4}\s*", "", copyright).strip()
        return label

    def _album_label(self, collection_id: str) -> str:
        try:
            results = self._lookup(collection_id)
            album = next(
                (
                    item
                    for item in results
                    if item.get("wrapperType") == "collection"
                ),
                None,
            )
            return self._label_from_copyright(album.get("copyright", "")) if album else ""
        except (KeyError, requests.RequestException, ValueError):
            return ""

    def _is_song(self, item: dict) -> bool:
        return item.get("wrapperType") == "track" and item.get("kind") == "song"
