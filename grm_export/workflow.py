import datetime
import json
import re
import traceback

from pathlib import Path
from typing import List, Dict, Generator, Iterable, AbstractSet

import enlighten
import gpxpy
import pgeocode
import pyproj
import requests
import rdp

import mapbox_vector_tile
import math
import diskcache

from grm_export.models import Feature, LatLon, TRF_Restrictions

clean_text_re = re.compile(r'[^\w\n\ \.\,]+')


# TODO: cachebuster / versioning
CACHE = diskcache.Cache(directory="_grmcache")


def pixel2deg(xtile, ytile, zoom, xpixel, ypixel, extent = 4096):
    # thanks stackoverflow
    # https://gis.stackexchange.com/questions/401541/decoding-mapbox-vector-tiles
    n = 2.0 ** zoom
    xtile = xtile + (xpixel / extent)
    ytile = ytile + ((extent - ypixel) / extent)
    lon_deg = (xtile / n) * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return (lon_deg, lat_deg)


def deg2num(lat_deg, lon_deg, zoom):
    # https://stackoverflow.com/questions/29218920/how-to-find-out-map-tile-coordinates-from-latitude-and-longitude

    # https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames#Lon./lat._to_tile_numbers
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (xtile, ytile)


def num2deg(xtile, ytile, zoom):
    # This returns the NW-corner of the square.
    # Use the function with xtile+1 and/or ytile+1
    # to get the other corners. With xtile+0.5 & ytile+0.5
    # it will return the center of the tile.
    n = 1 << zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def mapbox_source(centred: LatLon, radius: float) -> dict:
    # token is publicly available to guests and non-members
    access_token = "pk.eyJ1IjoidHJmZ3JtMjAyMyIsImEiOiJjbG9oc3NvYnoxazVpMmpwOXVrZWprNHQ5In0.k4qADdWyIfXxPsFr2JEI2w"
    dataset_id = "trfgrm2023.grrtilesv6"

    # we want to use a fixed zoom
    # because mapbox is lossy and uses 4096 ints to encode
    # all lat lon coords, for a given zoom level
    # so we need to be sufficiently zoomed in that the coords
    # are accurate enough for our purposes
    # without incurring too many api requests (2^n)

    starter_zoom = 11

    # figure out which tiles we need
    geod = pyproj.Geod(ellps="WGS84")
    N_lon, N_lat, _ = geod.fwd(centred.lon, centred.lat, 0, radius)
    S_lon, S_lat, _ = geod.fwd(centred.lon, centred.lat, 180, radius)
    W_lon, W_lat, _ = geod.fwd(centred.lon, centred.lat, 270, radius)
    E_lon, E_lat, _ = geod.fwd(centred.lon, centred.lat, 90, radius)

    N_x, N_y = deg2num(N_lat, N_lon, zoom=starter_zoom)
    S_x, S_y = deg2num(S_lat, S_lon, zoom=starter_zoom)
    W_x, W_y = deg2num(W_lat, W_lon, zoom=starter_zoom)
    E_x, E_y = deg2num(E_lat, E_lon, zoom=starter_zoom)

    # plus ones because we're looking at top left corners ... I think ...
    x_tiles = range(W_x, E_x+1)
    y_tiles = range(N_y, S_y+1)
    print("tile ranges", x_tiles, y_tiles)

    all_features = []

    for tile_zoom in [starter_zoom]:
        for tile_x in x_tiles:
            for tile_y in y_tiles:
                # TODO: this 'v6' stuff might be related to versioning, if they batch their updates
                #    try running this again in a month or so and see if there's any different data ...
                url = f"https://api.mapbox.com/v4/{dataset_id}/{tile_zoom}/{tile_x}/{tile_y}.vector.pbf"
                existing = CACHE.get(url)
                if existing is None:
                    print(f"query for {url}")
                    resp = requests.get(url, params=dict(access_token=access_token))

                    if resp.status_code == 404:
                        # no data for this tile
                        CACHE[url] = content = dict(
                            grrlayer=dict(extent=4096, features=[])
                        )
                    else:
                        pbuf = resp.content
                        transformer = lambda x, y: pixel2deg(tile_x, tile_y, tile_zoom, x, y)
                        try:
                            content = mapbox_vector_tile.decode(pbuf, transformer=transformer)
                        except Exception as e:
                            traceback.print_exc()
                            continue
                        else:
                            CACHE[url] = content
                    existing = content

                layer = existing["grrlayer"]
                assert layer["extent"] == 4096, f"extent should be 4096 but was {existing["extent"]}"
                all_features.extend(layer["features"])
    return dict(features=all_features)


def feature_gen(content: List[Dict]) -> Generator[Feature, None, None]:
    features = content["features"]
    for feature_data in features:
        p = feature_data["properties"]
        g = feature_data["geometry"]

        geometry_type = g["type"]
        if geometry_type == "MultiLineString":
            full_coords = g["coordinates"][0]
        elif geometry_type == "LineString":
            full_coords = g["coordinates"]
        else:
            raise Exception(f"can't handle geometry {feature_data}")

        full_coords = [d[0:2] for d in full_coords]  # strip out height/elevation third coord
        try:
            # https://gis.stackexchange.com/a/8674
            crush_coords = rdp.rdp(full_coords, epsilon=1e-4)  # maximum deviation
        except Exception:
            print(full_coords)
            raise

        yield Feature(
            # TODO: make crush thingy optional
            # coords=crush_coords,
            coords=full_coords,
            grm_class=TRF_Restrictions(p["class"]),
            # color=p["color"],
            # county=p["county"],  # unneeded
            # desc=p["desc"],
            grmuid=int(p.get("grmuid", feature_data["id"])),
            # ha=p["ha"],
            # har=p["har"],
            # historical=p["historical"],
            # length=int(p["length"]),
            membermessage=p.get("membermessage", "unknown message"),
            name=p.get("name", "unknown name"),
            # no_through_route=bool(int(p["no_through_route"])),
            # type=p["type"],
            geometry_type=geometry_type,
            # usrn=p["usrn"],
            original_coord_length=len(full_coords),
        )


def geo_deref(uk_post_code: str) -> LatLon:
    nomi = pgeocode.Nominatim("GB")
    response = nomi.query_postal_code(uk_post_code)
    print(f"Generation centred on {response["place_name"]}, {response["county_name"]}")
    return LatLon(response["latitude"], response["longitude"])


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
    # if is_no_through is not None:
    #     keep = [
    #         f for f in keep if f.no_through_route == is_no_through
    #     ]
    return keep


def extract_from_mapbox(centred_on: LatLon, radius: float, pbar_manager: enlighten.Manager) -> List[Feature]:
    geojson_data = mapbox_source(centred_on, radius)
    return extract_geojson(geojson_data, centred_on, radius, pbar_manager)


def extract_from_filepath(filepath: Path, centred_on: LatLon, radius: float, pbar_manager: enlighten.Manager) -> List[Feature]:
    geojson_data = json.loads(filepath.read_text())
    return extract_geojson(geojson_data, centred_on, radius, pbar_manager)


def extract_geojson(geojson: dict, centred_on: LatLon, radius: float, pbar_manager: enlighten.Manager) -> List[Feature]:
    geod = pyproj.Geod(ellps="WGS84")

    point_count = 0
    full_point_count = 0
    total_length = 0
    keepers = []

    progress_bar = pbar_manager.counter(total=len(geojson["features"]), color="blue", desc="Parse & compress routes")
    for f in feature_gen(geojson):
        progress_bar.update()
        distance = geod.inv(*reversed(f.centre), *reversed(centred_on))[-1]
        f.distance = distance
        if distance > radius:
            continue
        keepers.append(f)
        point_count += len(f.coords)
        full_point_count += f.original_coord_length
        total_length += getattr(f, "length", 0)
    progress_bar.clear()

    # TODO: Geod.line_length() from pyproj to calculate "true" length of the byway itself, check for discrepencies?

    # the compression ratio
    if full_point_count:
        cr = 100 * ((full_point_count - point_count) / full_point_count)
    else:
        cr = 0
    print(
        f"{len(keepers)} of {len(geojson['features'])} lanes selected, {point_count} gpx points (compressed from {full_point_count} {cr:.1f}% compression)")
    print(f"{total_length / 1000:.1f} km of lanes to ride")
    return keepers


def export(gpx: gpxpy.gpx.GPX):
    dest = Path(f"{gpx.name}.gpx")
    dest.write_text(gpx.to_xml())
    # print(f"check out:\nfile:///\"{dest}\"")
