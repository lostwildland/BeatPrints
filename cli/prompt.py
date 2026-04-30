import argparse
import re

import questionary

from rich import print

from cli import conf, exutils, validate
from BeatPrints import lyrics, spotify, poster, errors
from BeatPrints.providers import ITunesProvider

# Initialize components
ly = lyrics.Lyrics()
ps = poster.Poster(conf.POSTERS_DIR)


def is_direct_lookup(query: str) -> bool:
    """
    Returns True when the query is a direct music URL or Spotify URI.
    """
    value = query.strip()
    return bool(
        re.match(r"https?://", value)
        or re.fullmatch(r"spotify:(track|album):[0-9A-Za-z]{22}", value)
    )


def get_provider(provider_name: str):
    """
    Creates the selected metadata provider.
    """
    provider = provider_name.lower()

    if provider == "itunes":
        return ITunesProvider()

    if provider == "spotify":
        if not conf.CLIENT_ID or not conf.CLIENT_SECRET:
            print("Spotify credentials are required when provider is set to spotify.")
            exit(1)
        return spotify.Spotify(conf.CLIENT_ID, conf.CLIENT_SECRET)

    print(f"Unknown provider: {provider_name}. Use 'itunes' or 'spotify'.")
    exit(1)


def select_track(provider, limit: int):
    """
    Prompt user to search and select a track.

    Args:
        limit (int): Max search results.

    Returns:
        TrackMetadata: The selected track.
    """
    repeat = True

    while repeat:
        query = questionary.text(
            "• Type the track you love most, or paste a track URL:",
            validate=validate.LengthValidator,
            style=exutils.lavish,
            qmark="🎺",
        ).unsafe_ask()

        result = provider.get_track(query, limit=limit)
        direct = is_direct_lookup(query)

        # Clear the screen
        exutils.clear()

        if direct:
            print(f'Using "{result[0].name}" by {result[0].artist}.')
            return result[0]

        # Show results
        print(f'{len(result)} results found for "{query}"!')
        print(exutils.tablize_items(result, "track"))

        # Repeat search if needed
        repeat = questionary.confirm(
            "• Not what you wanted? Search again?",
            default=True,
            style=exutils.lavish,
            qmark="🤷",
        ).unsafe_ask()

        # Select track
        if not repeat:
            choice = questionary.text(
                f"• Select the track you like:",
                validate=validate.NumericValidator(limit=len(result)),
                style=exutils.lavish,
                qmark="🍀",
            ).unsafe_ask()

            exutils.clear()
            return result[int(choice) - 1]


def select_album(provider, limit: int):
    """
    Prompt user to search and select an album.

    Args:
        limit (int): Max search results.

    Returns:
        AlbumMetadata: The selected album.
    """
    repeat = True

    # Options for track numbering and shuffling
    index = questionary.confirm(
        "• Number the tracks?", style=exutils.lavish, qmark="🍙"
    ).unsafe_ask()

    shuffle = questionary.confirm(
        "• Shuffle the tracks?", style=exutils.lavish, qmark="🚀"
    ).unsafe_ask()

    while repeat:
        query = questionary.text(
            "• Type the album you love most, or paste an album URL:",
            validate=validate.LengthValidator,
            style=exutils.lavish,
            qmark="💿️",
        ).unsafe_ask()

        result = provider.get_album(query, limit, shuffle)
        direct = is_direct_lookup(query)

        # Clear the screen
        exutils.clear()

        if direct:
            print(f'Using "{result[0].name}" by {result[0].artist}.')
            return result[0], index

        # Show results
        print(f'{len(result)} results found for "{query}"!')
        print(exutils.tablize_items(result, "album"))

        # Repeat search if needed
        repeat = questionary.confirm(
            "• Not what you wanted? Search again?",
            default=True,
            style=exutils.lavish,
            qmark="🤷",
        ).unsafe_ask()

        # Select album
        if not repeat:
            choice = questionary.text(
                f"• Select the album you like:",
                validate=validate.NumericValidator(limit=len(result)),
                style=exutils.lavish,
                qmark="🍀",
            ).unsafe_ask()

            exutils.clear()
            return result[int(choice) - 1], index


def handle_lyrics(track: spotify.TrackMetadata):
    """
    Get lyrics and let user select lines.

    Args:
        track (TrackMetadata): Track for lyrics.

    Returns:
        str: Selected lyrics portion.
    """
    try:
        # Fetch lyrics and print it in a pretty table
        lyrics = ly.get_lyrics(track)

        if ly.check_instrumental(track):
            print("🎸 • The track is detected to be an instrumental track")
            return lyrics

        print(exutils.format_lyrics(track.name, track.artist, lyrics))

        # Let user pick lyrics lines
        selection_range = questionary.text(
            "• Select 4 of your favorite lines (e.g., 2-5, 7-10):",
            validate=validate.SelectionValidator(lyrics),
            style=exutils.lavish,
            qmark="🎀",
        ).unsafe_ask()

        return ly.select_lines(lyrics, selection_range)

    except errors.NoLyricsAvailable:
        print("😦 • Couldn't find the lyrics with LRClib.")
        print("╰─ You can try getting them from other sources!")

        # Ask user to paste custom lyrics
        lyrics = questionary.text(
            "• Paste your lyrics here:",
            validate=validate.LineValidator,
            multiline=True,
            style=exutils.lavish,
            qmark="🎀",
        ).unsafe_ask()

        return lyrics


def poster_features():
    """
    Ask for poster customization options.

    Returns:
        tuple: theme, accent color, and image path.
    """
    features = questionary.form(
        theme=questionary.select(
            "• Which theme do you prefer?",
            choices=[
                "Light",
                "Dark",
                "Catppuccin",
                "Gruvbox",
                "Nord",
                "RosePine",
                "Everforest",
            ],
            default="Light",
            style=exutils.lavish,
            qmark="💫",
        ),
        accent=questionary.confirm(
            "• Add a colored accent to the bottom?",
            default=False,
            style=exutils.lavish,
            qmark="🌈",
        ),
        image=questionary.confirm(
            "• Use a custom image as the poster's cover art?",
            default=False,
            style=exutils.lavish,
            qmark="🥐",
        ),
    ).unsafe_ask()

    theme, accent, image = features.values()

    # Get the image path if custom image is selected
    image_path = (
        questionary.path(
            "• Provide the file path to the image:",
            validate=validate.ImagePathValidator,
            style=exutils.lavish,
            qmark="╰─",
        )
        .skip_if(not image, default=None)
        .unsafe_ask()
    )

    return theme, accent, image_path


def create_poster(provider_name: str, code_mode: str):
    """
    Create a poster based on user input.
    """
    poster_type = questionary.select(
        "• What do you want to create?",
        choices=["Track Poster", "Album Poster"],
        style=exutils.lavish,
        qmark="🎨",
    ).unsafe_ask()

    theme, accent, image = poster_features()
    provider = get_provider(provider_name)

    # Clear the screen
    exutils.clear()

    # Generate posters
    if poster_type == "Track Poster":
        track = select_track(provider, conf.SEARCH_LIMIT)

        if track:
            lyrics = handle_lyrics(track)

            exutils.clear()
            ps.track(track, lyrics, accent, theme, image, code=code_mode)
    else:
        album = select_album(provider, conf.SEARCH_LIMIT)

        if album:
            ps.album(*album, accent, theme, image, code=code_mode)


def main():
    exutils.clear()

    try:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--provider",
            choices=["itunes", "spotify"],
            default=conf.PROVIDER,
            help="Metadata provider to use.",
        )
        parser.add_argument(
            "--code",
            choices=["auto", "spotify", "none"],
            default=conf.CODE_MODE,
            help="Poster code area behavior.",
        )
        args = parser.parse_args()

        create_poster(args.provider, args.code)
    except KeyboardInterrupt:
        exutils.clear()
        print("👋 Alright, no problem! See you next time.")
        exit(1)
