import datetime
import json
import pprint
from operator import attrgetter
import re

import gpxpy
import pyproj
import pgeocode
from dataclasses import dataclass

from pathlib import Path
from typing import List, Dict, Generator, Tuple, Iterable

clean_text_re = re.compile('[^\w\n\ \.\,]+')
LatLon = Tuple[float, float]

@dataclass
class Feature:
    coords: List[List[float]]
    grm_class: str
    color: str
    county: str
    desc: str
    grmuid: int
    ha: str
    har: str
    historical: str
    length: int
    membermessage: str
    name: str
    no_through_route: str
    type: str
    usrn: str

    @property
    def can_use(self):
        """can we actually use this byway"""
        if int(self.no_through_route):
            return False

        return True

    @property
    def centre(self) -> LatLon:
        return self.coords[0][1], self.coords[0][0]

    @property
    def distance(self) -> float:
        return self._distance

    @distance.setter
    def distance(self, val: float):
        self._distance = val


def feature_gen(content: List[Dict]) -> Generator[Feature, None, None]:
    for feature_data in content["features"]:
        p = feature_data["properties"]
        yield Feature(
            coords=feature_data["geometry"]["coordinates"],
            grm_class=p["class"],
            color=p["color"],
            county=p["county"],
            desc=p["desc"],
            grmuid=int(p["grmuid"]),
            ha=p["ha"],
            har=p["har"],
            historical=p["historical"],
            length=int(p["length"]),
            membermessage=p["membermessage"],
            name=p["name"],
            no_through_route=p["no_through_route"],
            type=p["type"],
            usrn=p["usrn"],
        )


def geo_deref(uk_post_code:str) -> LatLon:
    nomi = pgeocode.Nominatim("GB")
    response = nomi.query_postal_code(uk_post_code)
    pprint.pprint(response)
    return response["latitude"], response["longitude"]


def as_gpx(features: Iterable[Feature], title: str, multi_track: bool) -> gpxpy.gpx.GPX:
    gpx = gpxpy.gpx.GPX()
    gpx.name = title
    gpx.description = "This is an export from the TRF green roads map"
    gpx.author_name = "David Hyman"
    gpx.copyright_author = "David Hyman"
    gpx.copyright_year = str(datetime.datetime.utcnow().year)

    mega_gpx_track = gpxpy.gpx.GPXTrack(
        name=f"{title}",
        description=gpx.description
    )
    #
    # fake_time = datetime.datetime.utcnow()
    # fake_point_incr = datetime.timedelta(seconds=1)
    # fake_track_incr = datetime.timedelta(hours=1)

    for feature in features:
        _desc = f"{title}\n\n{feature.membermessage}"
        _desc = clean_text_re.sub("|", _desc).strip()
        pprint.pprint(_desc)
        gpx_track = gpxpy.gpx.GPXTrack(
            name=f"{feature.grmuid} {feature.name}",
            description=_desc
        )

        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        for coords in feature.coords:
            # TODO: provide accessor for LatLon to avoid confusion
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(coords[1], coords[0]))
            # fake_time += fake_point_incr
        pprint.pprint(f"{feature.name} {gpx_segment.length_2d():.1f}")
        # fake_time += fake_track_incr
        mega_gpx_track.segments.append(gpx_segment)
        if multi_track:
            gpx_track.segments.append(gpx_segment)
            gpx.tracks.append(gpx_track)

    if not multi_track:
        gpx.tracks.append(mega_gpx_track)

    return gpx


def extract(filepath: Path, postcode: str, radius: float) -> List[Feature]:
    centred_on = geo_deref(postcode)
    content = json.loads(filepath.read_text())
    geod = pyproj.Geod(ellps="WGS84")

    keepers = []
    for f in feature_gen(content):
        distance = geod.inv(*reversed(f.centre), *reversed(centred_on))[-1]
        f.distance = distance
        if distance > radius:
            continue
        if not f.can_use:
            continue
        keepers.append(f)

    for f in sorted(keepers, key=attrgetter("distance")):
        print(f"{f.grmuid}\t{f.distance/1000:.2f}km\t{f.name}\t{f.membermessage[:64]}")

    print(f"{len(keepers)} segments selected (of {len(content['features'])})")
    return keepers


def export(gpx: gpxpy.gpx.GPX):
    dest = Path(f"{gpx.name}.gpx")
    dest.write_text(gpx.to_xml())
    print(f"check out:\nfile:///\"{dest}\"")


def run():
    postcode = "GL9 1"
    radius = 60e3
    features = extract(Path("results3.json"), postcode, radius)
    title = f"{postcode} {radius / 1000:.0f}km - TRF GRM export mega"
    export(as_gpx(features, title, False))
    title = f"{postcode} {radius / 1000:.0f}km - TRF GRM export multi"
    export(as_gpx(features, title, True))


__name__ == "__main__" and run()
