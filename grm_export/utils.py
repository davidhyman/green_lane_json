import datetime
import getpass
import re
from pathlib import Path

import diskcache


def get_cache() -> diskcache.Cache:
    today = datetime.datetime.today()
    # TODO: just use expiry?
    cache_dir = f"_grmcache/year_{today.year}_week_{today.isocalendar().week}"
    return diskcache.Cache(directory=cache_dir)


def default_author() -> str:
    """use the current user as the author"""
    return getpass.getuser().title()


def looks_like_key(candidate: str) -> bool:
    return candidate.startswith("pk") and len(candidate.split("."))==3


def mapbox_key_from_dir(path: Path) -> str:
    if not path.exists():
        raise ValueError(f"this file or directory doesn't exist: {path}")
    finder = re.compile(r"api.mapbox.*access_token=([\w\.]+)")
    key = None
    for filepath in path.rglob("**/combined.js.php"):
        for encoding in ("latin", "utf8", "cp1140", "cp1252"):  # who knows?
            try:
                print(f"trying ({encoding}): {filepath}")
                content = filepath.read_text(encoding=encoding)
                maybe_match = finder.search(content)
                if maybe_match:
                    key = maybe_match.groups()[0]
                    break
            except (ValueError, PermissionError) as e:
                print(f"{e.__class__} couldn't read {filepath}: {e}")
        if key:
            break
    else:
        raise KeyError(f"couldn't find the key in {path}")
    print(f"found key: {key[:8]}***, looks valid: {looks_like_key(key)}")
    return key
