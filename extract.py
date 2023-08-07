import datetime
import json
import pprint
from operator import attrgetter
import re

import rdp
import gpxpy
import pyproj
import enlighten
import pgeocode
from functools import cached_property
from dataclasses import dataclass

from pathlib import Path
from typing import List, Dict, Generator, Tuple, Iterable, Optional, NamedTuple

clean_text_re = re.compile('[^\w\n\ \.\,]+')

class LatLon(NamedTuple):
    lat: float
    lon: float

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

    original_coord_length: int

    @cached_property
    def poly_line(self) -> List[LatLon]:
        return [LatLon(c[1], c[0]) for c in self.coords]
    
    def compressed_poly_line(self, epsilon:float=5e-5) -> List[LatLon]:
        # https://gis.stackexchange.com/a/8674
        crushed = rdp.rdp(self.poly_line, epsilon=epsilon)  # maximum deviation
        return [LatLon(*c) for c in crushed]
    
    @property
    def can_use(self):
        """can we actually use this byway"""
        if self.grm_class == "restricted":
            return False

        return True

    @property
    def centre(self) -> LatLon:
        line = self.poly_line
        return line[len(line)//2]

    @property
    def distance(self) -> float:
        return self._distance

    @distance.setter
    def distance(self, val: float):
        self._distance = val


def feature_gen(content: List[Dict]) -> Generator[Feature, None, None]:
    features = content["features"]
    pbar = enlighten.Counter(total=len(features), color="blue")
    for feature_data in features:
        p = feature_data["properties"]

        full_coords = feature_data["geometry"]["coordinates"]
        full_coords = [d[0:2] for d in full_coords]  # strip out height/elevation third coord
        try:
            # https://gis.stackexchange.com/a/8674
            crush_coords = rdp.rdp(full_coords, epsilon=5e-5)  # maximum deviation
        except Exception:
            print(full_coords)
            raise

        yield Feature(
            coords=crush_coords,
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
            original_coord_length=len(full_coords),
        )

        pbar.update()


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

    pbar = enlighten.Counter(total=len(features), color="green")
    for feature in features:
        _desc = f"{title}\n\n{feature.membermessage}"
        _desc = clean_text_re.sub("|", _desc).strip()
        # pprint.pprint(_desc)
        gpx_track = gpxpy.gpx.GPXTrack(
            name=f"{feature.grmuid} {feature.name}",
            description=_desc
        )

        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        for coord in feature.poly_line:
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(latitude=coord.lat, longitude=coord.lon))
            # fake_time += fake_point_incr
        # pprint.pprint(f"{feature.name} {gpx_segment.length_2d():.1f}")
        # fake_time += fake_track_incr
        mega_gpx_track.segments.append(gpx_segment)
        if multi_track:
            gpx_track.segments.append(gpx_segment)
            gpx.tracks.append(gpx_track)

        pbar.update()

    if not multi_track:
        gpx.tracks.append(mega_gpx_track)

    return gpx


def extract(filepath: Path, postcode: str, radius: float) -> List[Feature]:
    centred_on = geo_deref(postcode)
    content = json.loads(filepath.read_text())
    geod = pyproj.Geod(ellps="WGS84")

    point_count = 0
    full_point_count = 0
    total_length = 0
    keepers = []
    skippers = []
    for f in feature_gen(content):
        distance = geod.inv(*reversed(f.centre), *reversed(centred_on))[-1]
        f.distance = distance
        if distance > radius:
            continue
        if not f.can_use:
            skippers.append(f)
            continue
        keepers.append(f)
        point_count += len(f.coords)
        full_point_count += f.original_coord_length
        total_length += f.length


    # TODO: Geod.line_length() from pyproj to calculate length of the byway itself?

    for f in sorted(skippers, key=attrgetter("distance")):
        print(f"skip byway: {f.grmuid}\t{f.distance/1000:.2f}km away\t{f.length}\t{f.name}\t{f.membermessage[:64]}")


    # for f in sorted(keepers, key=attrgetter("distance")):
    #     print(f"{f.grmuid}\t{f.distance/1000:.2f}km\t{f.name}\t{f.membermessage[:64]}")

    cr = 100*((full_point_count - point_count) / full_point_count)
    print(f"{len(keepers)} segments, {point_count}(compressed from {full_point_count} {cr:.1f}%) points selected (of {len(content['features'])} lanes)")
    print(f"{total_length/1000} km of lanes to ride (???)")
    return keepers


def export(gpx: gpxpy.gpx.GPX):
    dest = Path(f"{gpx.name}.gpx")
    dest.write_text(gpx.to_xml())
    print(f"check out:\nfile:///\"{dest}\"")


def run():
    postcode = "GL9 1"
    radius = 60e3
    features = extract(Path("results3.json"), postcode, radius)
    short_postcode = postcode.replace(" ", "")
    short_date = datetime.date.today().isoformat()
    title = f"TRF GRM mono - {short_postcode} {radius / 1000:.0f}km {short_date}"
    export(as_gpx(features, title, False))
    title = f"TRF GRM multi - {short_postcode} {radius / 1000:.0f}km {short_date}"
    export(as_gpx(features, title, True))


__name__ == "__main__" and run()
