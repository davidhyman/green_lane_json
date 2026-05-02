import datetime

import enlighten

from grm_export.models import Config, TRF_Restrictions
from grm_export.poly import path_to_poly
from grm_export.workflow import (
    as_gpx,
    export,
    filter_by,
    geo_deref, mapbox_tiles_for_extent, mapbox_source, extract_geojson,
)


def run():
    manager = enlighten.get_manager()
    p_status = manager.status_bar("Preparing", justify=enlighten.Justify.CENTER)
    p_count = manager.counter(total=4, color="green", desc="Progress")
    p_count.update()

    config = Config()  # Parse the Command Line Interface

    p_status.update("Extracting JSON")
    p_count.update()

    centred_on = geo_deref(config.postcode)
    short_postcode = config.postcode.replace(" ", "").upper()
    if isinstance(config.region_or_radius, int):
        within = (centred_on, config.region_or_radius)
        short_name =  f"{short_postcode} {config.region_or_radius / 1000:.0f}km"
    else:
        within = path_to_poly(config.region_or_radius)
        short_name = f"{short_postcode} ({config.region_or_radius.stem})"

    tiles = mapbox_tiles_for_extent(within)
    geojson_data = mapbox_source(tiles, config.mapbox_key)
    all_features = extract_geojson(geojson_data, within, manager)

    p_status.update("Filter lanes by type")
    p_count.update()

    filtered_feature_groups = {
        # split good lanes into normal and dead-ends
        "good": filter_by(
            all_features,
            select_classes={TRF_Restrictions.FULL_ACCESS},
            deselect_classes=None,
            is_no_through=False,
        ),
        # TODO: to handle deadend again, we'd need to query the TRF server directly
        # "deadend": filter_by(all_features, select_classes={TRF_Restrictions.FULL_ACCESS}, deselect_classes=None,
        #           is_no_through=True),
        # split bad lanes into "very bad" and "dubious"
        "dubious": filter_by(
            all_features,
            select_classes=None,
            deselect_classes={
                TRF_Restrictions.FULL_ACCESS,
                TRF_Restrictions.RESTRICTED,
            },
            is_no_through=None,
        ),
        "closed": filter_by(
            all_features,
            select_classes={TRF_Restrictions.RESTRICTED},
            deselect_classes=None,
            is_no_through=None,
        ),
    }

    filtered_feature_groups["not_closed"] = filter_by(
        all_features,
        select_classes=None,
        deselect_classes={TRF_Restrictions.RESTRICTED},
        is_no_through=None,
    )



    short_date = datetime.date.today().isoformat()

    p_status.update("Generating GPX datasets")
    p_count.update()

    for filter_name, features in filtered_feature_groups.items():
        print(f"{filter_name} - {len(features)}")

    progress_bar = manager.counter(
        total=len(filtered_feature_groups) * 2, color="blue", desc="Write GPX"
    )
    for is_multi_track in (True, False):
        for filter_name, features in filtered_feature_groups.items():
            multi_name = "multi" if is_multi_track else "mono"
            title = f"TRF {short_name} {short_date} - {filter_name} {multi_name}"
            export(as_gpx(features, title, is_multi_track, config.author, manager))
            progress_bar.update()

    progress_bar.clear()

    p_status.update("Complete")
    p_count.update()

    p_status.clear()
    p_count.clear()
    manager.stop()


__name__ == "__main__" and run()
