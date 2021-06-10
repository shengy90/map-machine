from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
import svgwrite

from roentgen.constructor import Constructor
from roentgen.flinger import Flinger
from roentgen.icon import ShapeExtractor
from roentgen.mapper import TAGS_FILE_NAME, ICONS_FILE_NAME, Painter
from roentgen.osm_getter import get_osm
from roentgen.osm_reader import Map, OSMReader
from roentgen.scheme import Scheme
from roentgen.ui import error
from roentgen.util import MinMax


@dataclass
class Tile:
    x: int
    y: int
    scale: int

    @classmethod
    def from_coordinates(cls, coordinates: np.array, scale: int):
        """
        Code from https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
        """
        lat_rad = np.radians(coordinates[0])
        n: float = 2.0 ** scale
        x: int = int((coordinates[1] + 180.0) / 360.0 * n)
        y: int = int((1.0 - np.arcsinh(np.tan(lat_rad)) / np.pi) / 2.0 * n)
        return cls(x, y, scale)

    def get_coordinates(self) -> np.array:
        """
        Return geo coordinates of the north-west corner of the tile.

        Code from https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
        """
        n: float = 2.0 ** self.scale
        lon_deg: float = self.x / n * 360.0 - 180.0
        lat_rad: float = np.arctan(np.sinh(np.pi * (1 - 2 * self.y / n)))
        lat_deg: np.ndarray = np.degrees(lat_rad)
        return np.array((lat_deg, lon_deg))

    def get_boundary_box(self) -> Tuple[np.array, np.array]:
        return (
            self.get_coordinates(),
            Tile(self.x + 1, self.y + 1, self.scale).get_coordinates(),
        )

    def get_extended_boundary_box(self) -> Tuple[np.array, np.array]:
        lat1, lon1 = self.get_coordinates()
        lat2, lon2 = Tile(self.x + 1, self.y + 1, self.scale).get_coordinates()
        return (
            np.array((int(lat1 * 1000) / 1000 + 0.002, int(lon1 * 1000) / 1000 - 0.001)),
            np.array((int(lat2 * 1000) / 1000 - 0.001, int(lon2 * 1000) / 1000 + 0.002)),
        )

    def load_map(self) -> Optional[Map]:
        coordinates_1, coordinates_2 = self.get_extended_boundary_box()
        lat1, lon1 = coordinates_1
        lat2, lon2 = coordinates_2

        boundary_box: str = (
            f"{min(lon1, lon2):.3f},{min(lat1, lat2):.3f},"
            f"{max(lon1, lon2):.3f},{max(lat1, lat2):.3f}"
        )
        content = get_osm(boundary_box)
        if not content:
            error("cannot download OSM data")
            return None

        input_file_name = "map" / Path(boundary_box + ".osm")

        osm_reader = OSMReader()
        osm_reader.parse_osm_file(input_file_name)

        return osm_reader.map_

    def get_map_name(self, directory_name: Path) -> Path:
        return directory_name / f"tile_{self.scale}_{self.x}_{self.y}.svg"

    def get_carto_address(self) -> str:
        """
        Get URL of this tile from the OpenStreetMap server.
        """
        return (
            f"https://tile.openstreetmap.org/{self.scale}/{self.x}/{self.y}.png"
        )

    def draw(self, directory_name: Path):

        map_ = self.load_map()

        lat1, lon1 = self.get_coordinates()
        lat2, lon2 = Tile(self.x + 1, self.y + 1, self.scale).get_coordinates()

        min_ = np.array((min(lat1, lat2), min(lon1, lon2)))
        max_ = np.array((max(lat1, lat2), max(lon1, lon2)))

        flinger: Flinger = Flinger(MinMax(min_, max_), self.scale)
        size: np.array = flinger.size

        output_file_name = self.get_map_name(directory_name)

        svg: svgwrite.Drawing = svgwrite.Drawing(
            str(output_file_name), size=size
        )
        icon_extractor: ShapeExtractor = ShapeExtractor(
            Path(ICONS_FILE_NAME), Path("icons/config.json")
        )
        scheme: Scheme = Scheme(Path(TAGS_FILE_NAME))
        constructor: Constructor = Constructor(
            map_, flinger, scheme, icon_extractor
        )
        constructor.construct()

        painter: Painter = Painter(
            map_=map_,
            flinger=flinger,
            svg=svg,
            icon_extractor=icon_extractor,
            scheme=scheme,
        )
        painter.draw(constructor)

        print(f"Writing output SVG {output_file_name}...")
        with output_file_name.open("w") as output_file:
            svg.write(output_file)


if __name__ == '__main__':
    directory = Path("tiles")
    directory.mkdir(exist_ok=True)
    tile18 = Tile.from_coordinates(np.array((55.73, 37.62)), 18)
    tile18.draw(directory)
    Tile(tile18.x + 1, tile18.y + 0, 18).draw(directory)
    Tile(tile18.x + 0, tile18.y - 1, 18).draw(directory)
    Tile(tile18.x + 1, tile18.y - 1, 18).draw(directory)
