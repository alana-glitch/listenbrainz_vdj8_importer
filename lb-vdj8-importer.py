#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025 maximizzar <mail@maximizzar.de>
#
# SPDX-License-Identifier: GPL-3.0-or-later
import re
import sys
import os

import typer
import liblistenbrainz
import toml

from datetime import datetime, timezone
from pathlib import Path
from platformdirs import user_config_dir

from liblistenbrainz.errors import (
    ListenBrainzAPIException,
    InvalidSubmitListensPayloadException,
    InvalidAuthTokenException,
)
from tabulate import tabulate


def print_listens(listens: list[liblistenbrainz.Listen]):
    """
    Print a table of all listens
    :param listens: a list of liblistenbrainz.Listen objects
    """
    table_data = []
    for L in listens:
        table_data.append(
            {
                "artist": L.artist_name,
                "track": L.track_name,
                "time": datetime.fromtimestamp(L.listened_at, tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        )
    print(
        tabulate(
            table_data, headers="keys", tablefmt="grid", maxcolwidths=[20, 20, None]
        )
    )


def parse_extvdj_line(line) -> liblistenbrainz.Listen | None:
    """
    Parse a #EXTVDJ line and return a dict with fields. Example line:\n
    #EXTVDJ:<filesize>33268928</filesize><lastplaytime>1672704055</lastplaytime><artist>S3RL feat Sara</artist><title>Techno Kitty</title><songlength>224.482</songlength>
    """

    pattern = re.compile(r"<(\w+)>(.*?)</\1>")
    fields = dict(pattern.findall(line))

    listen: liblistenbrainz.Listen = liblistenbrainz.Listen(
        artist_name=fields.get("artist"),
        track_name=fields.get("title"),
        listened_at=int(fields.get("lastplaytime")),
        listening_from="VirtualDJ",
        additional_info={"media_player": "VirtualDJ"},
    )

    if listen.artist_name and listen.track_name:
        return listen
    return None


def parse_vdj_playlist(playlist_file) -> list[liblistenbrainz.Listen]:
    listens: list[liblistenbrainz.Listen] = []

    with open(playlist_file, "r", encoding="utf-8") as playlist:
        for line in playlist:
            line = line.strip()
            if not line.startswith("#EXTVDJ"):
                continue
            listen: liblistenbrainz.Listen = parse_extvdj_line(line)

            if not listen:
                continue

            listens.append(listen)

    return listens


def main(
    playlists: list[Path],
    yes: bool = typer.Option(False, "--yes", "-y", help="Submit without confirmation"),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Don't show information about submitted data"
    ),
):
    app_name = "listenbrainz_vdj8_importer"
    config_dir = user_config_dir(app_name)
    os.makedirs(config_dir, exist_ok=True)
    config_file = os.path.join(config_dir, "config.toml")

    try:
        config = toml.load(config_file)
    except FileNotFoundError:
        print(f"The config file {config_file} does not exist", file=sys.stderr)
        exit(1)
    user_token = config["listenbrainz"]["user_token"]

    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    client = liblistenbrainz.ListenBrainz()

    try:
        client.set_auth_token(user_token)
    except InvalidAuthTokenException as invalid_auth_token_exception:
        print(f"The token is invalid: {invalid_auth_token_exception}")
        exit(1)
    except ListenBrainzAPIException as api_exception:
        print(
            f"The ListenBrainz API encountered an error: {api_exception}",
            file=sys.stderr,
        )

    has_error = False

    for playlist in playlists:
        if not playlist.exists():
            print(f"The playlist {playlist} does not exist", file=sys.stderr)
            exit(1)

        print(f"Processing playlist: {playlist}")
        listens = parse_vdj_playlist(playlist)
        if len(listens) == 0:
            print("No listens found", file=sys.stderr)

        if not quiet:
            print_listens(listens)

        if yes:
            client.submit_multiple_listens(listens)
            continue

        if not interactive:
            print("Can't ask for confirmation, exiting", file=sys.stderr)
            exit(1)

        response = input("Do you want to submit your listens? [Y/n] ").strip().lower()
        if response in ("", "y", "yes"):
            try:
                client.submit_multiple_listens(listens)
            except ListenBrainzAPIException as api_exception:
                print(
                    f"The ListenBrainz API encountered an error: {api_exception}",
                    file=sys.stderr,
                )
                has_error = True
            except InvalidSubmitListensPayloadException as payload_exception:
                print(
                    f"The ListenBrainz API rejected the payload: {payload_exception}",
                    file=sys.stderr,
                )
                has_error = True

    if has_error:
        exit(1)


if __name__ == "__main__":
    typer.run(main)
