import datetime
import json
import re

from pathlib import Path
from typing import List, Dict, Generator, Iterable, AbstractSet

import enlighten
import gpxpy
import pgeocode
import pyproj
import rdp

from extract.models import Feature, LatLon, TRF_Restrictions

clean_text_re = re.compile(r'[^\w\n\ \.\,]+')


def feature_gen(content: List[Dict]) -> Generator[Feature, None, None]:
    features = content["features"]
    for feature_data in features:
        p = feature_data["properties"]

        full_coords = feature_data["geometry"]["coordinates"]
        full_coords = [d[0:2] for d in full_coords]  # strip out height/elevation third coord
        try:
            # https://gis.stackexchange.com/a/8674
            crush_coords = rdp.rdp(full_coords, epsilon=1e-4)  # maximum deviation
        except Exception:
            print(full_coords)
            raise

        yield Feature(
            coords=crush_coords,
            grm_class=TRF_Restrictions(p["class"]),
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
            no_through_route=bool(int(p["no_through_route"])),
            type=p["type"],
            usrn=p["usrn"],
            original_coord_length=len(full_coords),
        )


def geo_deref(uk_post_code: str) -> LatLon:
    nomi = pgeocode.Nominatim("GB")
    response = nomi.query_postal_code(uk_post_code)
    print(f"Generation centred on {response["place_name"]}, {response["county_name"]}")
    return response["latitude"], response["longitude"]


def as_gpx(features: Iterable[Feature], title: str, multi_track: bool, author: str,
           pbar_manager: enlighten.Manager) -> gpxpy.gpx.GPX:
    gpx = gpxpy.gpx.GPX()
    gpx.name = title
    gpx.description = "This is an export from the TRF green roads map at https://beta.greenroadmap.org.uk/"
    gpx.author_name = author
    gpx.copyright_author = "Trail Riders Fellowship"
    gpx.copyright_year = str(datetime.datetime.utcnow().year)
    gpx.creator = "https://github.com/davidhyman/green_lane_json"

    mega_gpx_track = gpxpy.gpx.GPXTrack(
        name=f"{title}",
        description=gpx.description
    )
    # # once upon a time I thought we could force lanes to be ordered by time somehow
    # fake_time = datetime.datetime.utcnow()
    # fake_point_incr = datetime.timedelta(seconds=1)
    # fake_track_incr = datetime.timedelta(hours=1)

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

    if not multi_track:
        gpx.tracks.append(mega_gpx_track)

    return gpx


def filter_by(features: List[Feature], select_classes: AbstractSet[TRF_Restrictions] | None,
              deselect_classes: AbstractSet[TRF_Restrictions] | None, is_no_through: bool | None) -> List[Feature]:
    keep = features
    if select_classes is not None:
        keep = [
            f for f in keep if f.grm_class in select_classes
        ]
    if deselect_classes is not None:
        keep = [
            f for f in keep if f.grm_class not in deselect_classes
        ]
    if is_no_through is not None:
        keep = [
            f for f in keep if f.no_through_route == is_no_through
        ]
    return keep


def extract(filepath: Path, postcode: str, radius: float, pbar_manager: enlighten.Manager) -> List[Feature]:
    centred_on = geo_deref(postcode)
    content = json.loads(filepath.read_text())
    geod = pyproj.Geod(ellps="WGS84")

    point_count = 0
    full_point_count = 0
    total_length = 0
    keepers = []

    progress_bar = pbar_manager.counter(total=len(content["features"]), color="blue", desc="Parse & compress routes")
    for f in feature_gen(content):
        progress_bar.update()
        distance = geod.inv(*reversed(f.centre), *reversed(centred_on))[-1]
        f.distance = distance
        if distance > radius:
            continue
        keepers.append(f)
        point_count += len(f.coords)
        full_point_count += f.original_coord_length
        total_length += f.length
    progress_bar.clear()

    # TODO: Geod.line_length() from pyproj to calculate "true" length of the byway itself, check for discrepencies?

    # the compression ratio
    cr = 100 * ((full_point_count - point_count) / full_point_count)
    print(
        f"{len(keepers)} of {len(content['features'])} lanes selected, {point_count} gpx points (compressed from {full_point_count} {cr:.1f}% compression)")
    print(f"{total_length / 1000:.1f} km of lanes to ride")
    return keepers


def export(gpx: gpxpy.gpx.GPX):
    dest = Path(f"{gpx.name}.gpx")
    dest.write_text(gpx.to_xml())
    # print(f"check out:\nfile:///\"{dest}\"")
