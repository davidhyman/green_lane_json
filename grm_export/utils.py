import base64
import datetime
import getpass
import re
from urllib import request

import diskcache


def get_cache() -> diskcache.Cache:
    today = datetime.datetime.today()
    # TODO: just use expiry?
    cache_dir = f"_grmcache/year_{today.year}_week_{today.isocalendar().week}"
    return diskcache.Cache(directory=cache_dir)


def default_author() -> str:
    """use the current user as the author"""
    return getpass.getuser().title()


def handle_key() -> str:
    try:
        cache = get_cache()
        memod = cache.memoize()(mapbox_key)
        return memod()
    except Exception:
        raise RuntimeError("Could not find key in public, please provide it via CLI")


def mapbox_key() -> str:
    _from = "aHR0cHM6Ly9nYW1tYS5ncmVlbnJvYWRtYXAub3JnLnVrL2Fzc2V0cy9pbmRleC5vbC5qcw=="
    uri = base64.standard_b64decode(_from).decode("utf8")
    resp = request.urlopen(uri).read().decode("utf8")
    finder = re.compile(r"api.mapbox.*access_token=([\w\.]+)")
    key = finder.findall(resp).pop()
    print(f"found public key: ***{key[-6:]}")
    return key
