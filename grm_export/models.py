from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from typing import List, NamedTuple

from pydantic import Field, BaseModel, FiniteFloat
from pydantic_settings import BaseSettings, CliPositionalArg, SettingsConfigDict

from grm_export.utils import default_author, handle_key


class LatLon(BaseModel):
    lat: FiniteFloat
    lon: FiniteFloat


class TRF_Restrictions(StrEnum):
    # for the 'class' field
    # {'partial-access', 'disputed', 'link_road_with_access', 'temporary_tro', 'full-access', 'restricted'}
    PARTIAL_ACCESS = "partial-access"
    DISPUTED = "disputed"
    LINK_ROAD = "link_road_with_access"
    TEMPORARY_TRO = "temporary_tro"
    RESTRICTED = "restricted"
    FULL_ACCESS = "full-access"


class Config(BaseSettings):
    """
    Extracts gps traces from the TRF dataset.

    See README.md or https://github.com/davidhyman/green_lane_json for instructions.

    e.g. for 30km around Cambridge:

    trf_export.exe CB1 30000
    """

    model_config = SettingsConfigDict(cli_parse_args=True)

    # source_file: CliPositionalArg[Path] = Field(description='Location of source data file (.json).')
    postcode: CliPositionalArg[str] = Field(
        description='Postcode to center the circular filter on. e.g. AB123CD or "AB12 3CD"'
    )
    radius: CliPositionalArg[int] = Field(
        description="Radius around the postcode to filter by, in metres. e.g. 60000 would be 60km radius"
    )
    author: str = Field(
        default=default_author(),
        description='Set the author name for gpx files. Use quotes e.g. --author="Bobby Tables"',
    )
    mapbox_key: str = Field(
        default_factory=handle_key,
        description='Override the mapbox key (visit https://gamma.greenroadmap.org.uk/main.js and look for `access_key`).',
    )


@dataclass
class Feature:
    coords: List[List[float]]
    grm_class: TRF_Restrictions
    # color: str
    # county: str
    # desc: str
    grmuid: int
    # ha: str
    # har: str
    # historical: str
    # length: int
    membermessage: str
    name: str
    # no_through_route: bool
    # type: str
    geometry_type: str
    # usrn: str

    original_coord_length: int

    @cached_property
    def poly_line(self) -> List[LatLon]:
        return [LatLon(lat=c[1], lon=c[0]) for c in self.coords]

    @property
    def centre(self) -> LatLon:
        line = self.poly_line
        return line[len(line) // 2]

    @property
    def distance(self) -> float:
        return self._distance

    @distance.setter
    def distance(self, val: float):
        self._distance = val

    def __str__(self) -> str:
        return f"Lane: {self.grmuid}\t{self.distance / 1000:.2f}km away\t{self.length}\t{self.name}\t{self.membermessage[:64]}"


@dataclass
class Dataset:
    features: List[Feature]
    multi_track: bool
    display_name: str
