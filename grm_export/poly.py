import json
import textwrap
import warnings
from pathlib import Path

import kml2geojson
from shapely.geometry import shape
from shapely.geometry.polygon import Polygon


def path_to_poly(path: Path) -> Polygon:
    if path.suffix == ".kml":
        print("converting from kml")
        geojson = kml2geojson.main.convert(path)
        geojson = geojson.pop() if isinstance(geojson, list) else geojson  # not sure why it would be :-/
    elif path.suffix in (".json", ".geojson"):
        geojson = json.loads(path.read_text())
    else:
        raise ValueError(textwrap.dedent(
            f"""
            Don't know how to parse "{path.name}"
            We need geojson (.json / .geojson)
            or Google's KML (.kml)
            """
        ))
    # get the first feature from geojson
    features = geojson.get("features")
    if not features:
        raise ValueError(f'No geojson features in "{path.name}"')
    if len(features) > 1:
        warnings.warn(f'More than one geojson feature in "{path.name}" - we only use the first one')
    polygon: Polygon = shape(features.pop()["geometry"])
    if not isinstance(polygon, Polygon):
        raise ValueError(textwrap.dedent(
            f"""
            The geographic data in "{path.name}"
            Does not look like a Polygon (it's a {type(polygon)}). Try again!
            """
        ))
    return polygon
