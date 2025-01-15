import pathlib

from .methods import *
from .models import *


def needs_rebuild_db():
    import datetime
    import warnings

    import requests

    resp = requests.get(
        "https://api.github.com/repos/PokeAPI/pokeapi/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if resp.status_code != 200:
        warnings.warn(
            "Unable to fetch latest PokeAPI release from GitHub. Please check manually."
        )
        return None

    release = resp.json()
    if not dbfile.exists():
        return release

    mtime = dbfile.stat().st_mtime
    publish_ts = datetime.datetime.fromisoformat(release["published_at"]).timestamp()
    if publish_ts > mtime:
        return release

    return None
