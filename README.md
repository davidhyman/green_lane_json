# TRF GRM GPS extractor

Extracts gps traces from the Trail Riders Federation dataset for the Green Road Map.

This project is hosted on https://github.com/davidhyman/green_lane_json

# What is it?
Intended for use by registered TRF members to load routes into their GPS devices and hence access them
when offline in areas of poor internet connectivity, as commonly encountered in rural areas where these lanes
are found.

# What do I need?
Obtain the latest TRF json file at "https://beta.greenroadmap.org.uk/json/results3.json?1721653721440"

Obtain `trf_export.exe` from this project.

You need to be a logged in member to retrieve this. Use the F12 network tab in your browser to find it (the name or location may change over time).

It is recommended to name the file locally with the date so you can refer back to it and see how current it is.
The tool will output multiple files;
- multi - saves each track as an individual route, very poor performance on some devices, but most granularity.
- mono - saves all tracks together as sections under one route, much better performance but on some
  Garmin devices results in start/end points of sections being joined by straight lines (unusable...).
  Known to work well on "GPX viewer pro".

It also splits the routes into groups according to the TRO status, presently:
- `good`; ready to go!
- `closed`; closed (indefinitely?) see GRM for details
- `dubious`; any other category (e.g. seasonal TRO)
- `deadend`; safe to ride, but you'll have to double back
- `not_closed`; includes all of the above that's not `closed`

You may wish to import the groups and set different colours on your device, and/or pay special attention to their current legality at the time of your access.

You can probably use any GIS tools to view, edit and verify the output such as: Garmin Basecamp, Google MyMaps, Google Earth, etc.

Phone/tablet apps that probably work include; gaia, osmand, gpx viewer pro, outdooractive, dmd2, etc.

# Usage

Run this in a [terminal](https://towardsdatascience.com/a-quick-guide-to-using-command-line-terminal-96815b97b955):
```shell
trf_export.exe -h
```

Display the help:
```shell
trf_export.exe -h

Extracts gps traces from the TRF dataset. See README.md or https://github.com/davidhyman/green_lane_json for instructions.

positional arguments:
  SOURCE_FILE   Location of source data file (.json).
  POSTCODE      Postcode to center the circular filter on. e.g. AB123CD or "AB12 3CD"
  RADIUS        Radius around the postcode to filter by, in metres. e.g. 60000 would be 60km radius

options:
  -h, --help    show this help message and exit
  --author str  Set the author name for gpx files. Use quotes e.g. --author="Bobby Tables" (required)
```

Run on the TRF json for 30km around Cambridge (CB1):
```shell
.\dist\trf_export\trf_export.exe .\results3.json CB1 30000
```
This will then print some progress messages and deposit the .gpx files in the current directory.


# Disclaimer

There is no TRF content included in this project, it simply a processing tool.

Majority of meaningful content on TRF website is uploaded by users and volunteers from public domain council sources and therefore is not "owned" by the TRF.
However, to avoid proliferation of out-of-date copies of gpx data (and hence avoid misuse of closed or TRO'd routes etc)
it is strongly recommended that the output of this tool is not shared outside the TRF.

This tool falls under the TRF "acceptable use" criteria: "You may, for your own personal, non-commercial use only, do the following: a. retrieve, display and view the Content on a computer screen".
For more information see https://beta.greenroadmap.org.uk/terms-of-use.

You should probably check your route with the latest TRO status on the live GRM map before riding.

Tool is provided as-is and copyrighted to the author. No warranty given or liability accepted.
