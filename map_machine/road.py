"""
WIP: road shape drawing.
"""
from dataclasses import dataclass
from typing import Any, Optional, Union

import numpy as np
import svgwrite
from colour import Color
from svgwrite import Drawing
from svgwrite.filters import Filter
from svgwrite.path import Path
from svgwrite.shapes import Circle

from map_machine.drawing import PathCommands
from map_machine.flinger import Flinger
from map_machine.osm_reader import OSMNode, Tagged
from map_machine.scheme import RoadMatcher
from map_machine.vector import (
    Line,
    Polyline,
    compute_angle,
    norm,
    turn_by_angle,
)

__author__ = "Sergey Vartanov"
__email__ = "me@enzet.ru"

USE_BLUR: bool = False


@dataclass
class Lane:
    """
    Road lane specification.
    """

    width: Optional[float] = None  # Width in meters
    is_forward: Optional[bool] = None  # Whether lane is forward or backward
    min_speed: Optional[float] = None  # Minimal speed on the lane
    # "none", "merge_to_left", "slight_left", "slight_right"
    turn: Optional[str] = None
    change: Optional[str] = None  # "not_left", "not_right"
    destination: Optional[str] = None  # Lane destination

    def set_forward(self, is_forward: bool) -> None:
        """If true, lane is forward, otherwise it's backward."""
        self.is_forward = is_forward

    def get_width(self, scale: float) -> float:
        """Get lane width.  We use standard 3.7 m lane."""
        if self.width is None:
            return 3.7 * scale
        return self.width * scale


class RoadPart:
    """
    Line part of the road.
    """

    def __init__(
        self,
        point_1: np.ndarray,
        point_2: np.ndarray,
        lanes: list[Lane],
        scale: float,
    ) -> None:
        """
        :param point_1: start point of the road part
        :param point_2: end point of the road part
        :param lanes: lane specification
        """
        self.point_1: np.ndarray = point_1
        self.point_2: np.ndarray = point_2
        self.lanes: list[Lane] = lanes
        if lanes:
            self.width = sum(map(lambda x: x.get_width(scale), lanes))
        else:
            self.width = 1
        self.left_offset: float = self.width / 2
        self.right_offset: float = self.width / 2

        self.turned: np.ndarray = norm(
            turn_by_angle(self.point_2 - self.point_1, np.pi / 2)
        )
        self.right_vector: np.ndarray = self.turned * self.right_offset
        self.left_vector: np.ndarray = -self.turned * self.left_offset

        self.right_connection: Optional[np.ndarray] = None
        self.left_connection: Optional[np.ndarray] = None
        self.right_projection: Optional[np.ndarray] = None
        self.left_projection: Optional[np.ndarray] = None

        self.left_outer: Optional[np.ndarray] = None
        self.right_outer: Optional[np.ndarray] = None
        self.point_a: Optional[np.ndarray] = None
        self.point_middle: Optional[np.ndarray] = None

    def update(self) -> None:
        """Compute additional points."""
        if self.left_connection is not None:
            self.right_projection = (
                self.left_connection + self.right_vector - self.left_vector
            )
        if self.right_connection is not None:
            self.left_projection = (
                self.right_connection - self.right_vector + self.left_vector
            )
        if (
            self.left_connection is not None
            and self.right_connection is not None
        ):
            a = np.linalg.norm(self.right_connection - self.point_1)
            b = np.linalg.norm(self.right_projection - self.point_1)
            if a > b:
                self.right_outer = self.right_connection
                self.left_outer = self.left_projection
            else:
                self.right_outer = self.right_projection
                self.left_outer = self.left_connection
            self.point_middle = self.right_outer - self.right_vector

            max_: float = 100

            if np.linalg.norm(self.point_middle - self.point_1) > max_:
                self.point_a = self.point_1 + max_ * norm(
                    self.point_middle - self.point_1
                )
                self.right_outer = self.point_a + self.right_vector
                self.left_outer = self.point_a + self.left_vector
            else:
                self.point_a = self.point_middle

    def get_angle(self) -> float:
        """Get an angle between line and x axis."""
        return compute_angle(self.point_2 - self.point_1)

    def draw_normal(self, drawing: svgwrite.Drawing) -> None:
        """Draw some debug lines."""
        line: Path = drawing.path(
            ("M", self.point_1, "L", self.point_2),
            fill="none",
            stroke="#8888FF",
            stroke_width=self.width,
        )
        drawing.add(line)

    def draw_debug(self, drawing: svgwrite.Drawing) -> None:
        """Draw some debug lines."""
        line: Path = drawing.path(
            ("M", self.point_1, "L", self.point_2),
            fill="none",
            stroke="#000000",
        )
        drawing.add(line)
        line: Path = drawing.path(
            (
                "M", self.point_1 + self.right_vector,
                "L", self.point_2 + self.right_vector,
            ),
            fill="none",
            stroke="#FF0000",
            stroke_width=0.5,
        )  # fmt: skip
        drawing.add(line)
        line = drawing.path(
            (
                "M", self.point_1 + self.left_vector,
                "L", self.point_2 + self.left_vector,
            ),
            fill="none",
            stroke="#0000FF",
            stroke_width=0.5,
        )  # fmt: skip
        drawing.add(line)

        opacity: float = 0.4
        radius: float = 2

        if self.right_connection is not None:
            circle = drawing.circle(
                self.right_connection, 2.5, fill="#FF0000", opacity=opacity
            )
            drawing.add(circle)
        if self.left_connection is not None:
            circle = drawing.circle(
                self.left_connection, 2.5, fill="#0000FF", opacity=opacity
            )
            drawing.add(circle)

        if self.right_projection is not None:
            circle = drawing.circle(
                self.right_projection, 1.5, fill="#FF0000", opacity=opacity
            )
            drawing.add(circle)
        if self.left_projection is not None:
            circle = drawing.circle(
                self.left_projection, 1.5, fill="#0000FF", opacity=opacity
            )
            drawing.add(circle)

        if self.right_outer is not None:
            circle = drawing.circle(
                self.right_outer,
                3.5,
                stroke_width=0.5,
                fill="none",
                stroke="#FF0000",
                opacity=opacity,
            )
            drawing.add(circle)
        if self.left_outer is not None:
            circle = drawing.circle(
                self.left_outer,
                3.5,
                stroke_width=0.5,
                fill="none",
                stroke="#0000FF",
                opacity=opacity,
            )
            drawing.add(circle)

        if self.point_a is not None:
            circle = drawing.circle(self.point_a, radius, fill="#000000")
            drawing.add(circle)

        # self.draw_entrance(drawing, True)

    def draw(self, drawing: svgwrite.Drawing) -> None:
        """Draw road part."""
        if self.left_connection is not None:
            path_commands = [
                "M", self.point_2 + self.right_vector,
                "L", self.point_2 + self.left_vector,
                "L", self.left_connection,
                "L", self.right_connection,
                "Z",
            ]  # fmt: skip
            drawing.add(drawing.path(path_commands, fill="#CCCCCC"))

    def draw_entrance(
        self, drawing: svgwrite.Drawing, is_debug: bool = False
    ) -> None:
        """Draw intersection entrance part."""
        if (
            self.left_connection is not None
            and self.right_connection is not None
        ):
            path_commands = [
                "M", self.right_projection,
                "L", self.right_connection,
                "L", self.left_projection,
                "L", self.left_connection,
                "Z",
            ]  # fmt: skip
            if is_debug:
                path = drawing.path(
                    path_commands,
                    fill="none",
                    stroke="#880088",
                    stroke_width=0.5,
                )
                drawing.add(path)
            else:
                drawing.add(drawing.path(path_commands, fill="#88FF88"))

    def draw_lanes(self, drawing: svgwrite.Drawing, scale: float) -> None:
        """Draw lane delimiters."""
        for lane in self.lanes:
            shift = self.right_vector - self.turned * lane.get_width(scale)
            path = drawing.path(
                ["M", self.point_middle + shift, "L", self.point_2 + shift],
                fill="none",
                stroke="#FFFFFF",
                stroke_width=2,
                stroke_dasharray="7,7",
            )
            drawing.add(path)


class Intersection:
    """
    An intersection of the roads, that is described by its parts.  All first
    points of the road parts should be the same.
    """

    def __init__(self, parts: list[RoadPart]) -> None:
        self.parts: list[RoadPart] = sorted(parts, key=lambda x: x.get_angle())

        for index in range(len(self.parts)):
            next_index: int = 0 if index == len(self.parts) - 1 else index + 1
            part_1: RoadPart = self.parts[index]
            part_2: RoadPart = self.parts[next_index]
            line_1: Line = Line(
                part_1.point_1 + part_1.right_vector,
                part_1.point_2 + part_1.right_vector,
            )
            line_2: Line = Line(
                part_2.point_1 + part_2.left_vector,
                part_2.point_2 + part_2.left_vector,
            )
            intersection: np.ndarray = line_1.get_intersection_point(line_2)
            # if np.linalg.norm(intersection - part_1.point_2) < 300:
            part_1.right_connection = intersection
            part_2.left_connection = intersection
            part_1.update()
            part_2.update()

        for index in range(len(self.parts)):
            next_index: int = 0 if index == len(self.parts) - 1 else index + 1
            part_1: RoadPart = self.parts[index]
            part_2: RoadPart = self.parts[next_index]
            part_1.update()
            part_2.update()

            if (
                part_1.right_connection is None
                and part_2.left_connection is None
            ):
                part_1.left_connection = part_1.right_projection
                part_2.right_connection = part_2.left_projection
                part_1.left_outer = part_1.right_projection
                part_2.right_outer = part_2.left_projection

            part_1.update()
            part_2.update()

    def draw(self, drawing: svgwrite.Drawing, is_debug: bool = False) -> None:
        """Draw all road parts and intersection."""
        inner_commands = ["M"]
        for part in self.parts:
            inner_commands += [part.left_connection, "L"]
        inner_commands[-1] = "Z"

        outer_commands = ["M"]
        for part in self.parts:
            outer_commands += [part.left_connection, "L"]
            outer_commands += [part.left_outer, "L"]
            outer_commands += [part.right_outer, "L"]
        outer_commands[-1] = "Z"

        # for part in self.parts:
        #     part.draw_normal(drawing)

        if is_debug:
            drawing.add(
                drawing.path(outer_commands, fill="#0000FF", opacity=0.2)
            )
            drawing.add(
                drawing.path(inner_commands, fill="#FF0000", opacity=0.2)
            )

        for part in self.parts:
            if is_debug:
                part.draw_debug(drawing)
            else:
                part.draw_entrance(drawing)
        if not is_debug:
            # for part in self.parts:
            #     part.draw_lanes(drawing, scale)
            drawing.add(drawing.path(inner_commands, fill="#FF8888"))


class Road(Tagged):
    """
    Road or track on the map.
    """

    def __init__(
        self,
        tags: dict[str, str],
        nodes: list[OSMNode],
        matcher: RoadMatcher,
        flinger: Flinger,
    ) -> None:
        super().__init__(tags)
        self.nodes: list[OSMNode] = nodes
        self.matcher: RoadMatcher = matcher

        self.line: Polyline = Polyline(
            [flinger.fling(x.coordinates) for x in self.nodes]
        )
        self.width: Optional[float] = matcher.default_width
        self.lanes: list[Lane] = []

        if "lanes" in tags:
            try:
                self.width = int(tags["lanes"]) * 3.7
                self.lanes = [Lane()] * int(tags["lanes"])
            except ValueError:
                pass

        if "width:lanes" in tags:
            widths: list[float] = list(
                map(float, tags["width:lanes"].split("|"))
            )
            if len(widths) == len(self.lanes):
                for index, lane in enumerate(self.lanes):
                    lane.width = widths[index]

        number: int
        if "lanes:forward" in tags:
            number = int(tags["lanes:forward"])
            [x.set_forward(True) for x in self.lanes[-number:]]
        if "lanes:backward" in tags:
            number = int(tags["lanes:backward"])
            [x.set_forward(False) for x in self.lanes[:number]]

        if "width" in tags:
            try:
                self.width = float(tags["width"])
            except ValueError:
                pass

        self.layer: float = 0
        if "layer" in tags:
            self.layer = float(tags["layer"])

    def get_style(
        self, flinger: Flinger, is_border: bool, is_for_stroke: bool = False
    ) -> dict[str, Union[int, float, str]]:
        """Get road SVG style."""
        width: float
        if self.width is not None:
            width = self.width
        else:
            width = self.matcher.default_width

        border_width: float
        if is_border:
            color = self.get_border_color()
            border_width = 2.0
        else:
            color = self.get_color()
            border_width = 0.0

        extra_width: float = 0.0
        if is_border:
            if self.tags.get("bridge") == "yes":
                extra_width = 0.5
            if self.tags.get("ford") == "yes":
                extra_width = 2.0
            if self.tags.get("embankment") == "yes":
                extra_width = 4.0

        scale: float = flinger.get_scale(self.nodes[0].coordinates)
        style: dict[str, Union[int, float, str]] = {
            "fill": "none",
            "stroke": color.hex,
            "stroke-linecap": "butt",
            "stroke-linejoin": "round",
            "stroke-width": scale * width + extra_width + border_width,
        }
        if is_for_stroke:
            style["stroke-width"] = 2 + extra_width
        if is_border and self.tags.get("embankment") == "yes":
            style["stroke-dasharray"] = "1,3"
        if self.tags.get("tunnel") == "yes":
            if is_border:
                style["stroke-dasharray"] = "3,3"

        return style

    def get_filter(self, svg: Drawing, is_border: bool) -> Optional[Filter]:
        """Get blurring filter."""
        if not USE_BLUR:
            return None

        if is_border and self.tags.get("bridge") == "yes":
            filter_ = svg.defs.add(svg.filter())
            filter_.feGaussianBlur(in_="SourceGraphic", stdDeviation=2)
            return filter_

        return None

    def draw(self, svg: Drawing, flinger: Flinger, is_border: bool) -> None:
        """Draw road as simple SVG path."""
        filter_: Filter = self.get_filter(svg, is_border)

        style: dict[str, Union[int, float, str]] = self.get_style(
            flinger, is_border
        )
        path_commands: str = self.line.get_path()
        path: Path
        if filter_:
            path = Path(d=path_commands, filter=filter_.get_funciri())
        else:
            path = Path(d=path_commands)

        path.update(style)
        svg.add(path)

    def get_color(self) -> Color:
        """Get road main color."""
        color: Color = self.matcher.color
        if self.tags.get("tunnel") == "yes":
            color = Color(color, luminance=min(1, color.luminance + 0.2))
        return color

    def get_border_color(self) -> Color:
        """Get road border color."""
        color: Color = self.matcher.border_color
        if self.tags.get("bridge") == "yes":
            color = Color("#666666")
        if self.tags.get("ford") == "yes":
            color = Color("#88BBFF")
        if self.tags.get("embankment") == "yes":
            color = Color("#666666")
        return color

    def draw_lanes(self, svg: Drawing, flinger: Flinger, color: Color) -> None:
        """Draw lane separators."""
        scale: float = flinger.get_scale(self.nodes[0].coordinates)

        if len(self.lanes) < 2:
            return

        for index in range(1, len(self.lanes)):
            parallel_offset: float = scale * (
                -self.width / 2 + index * self.width / len(self.lanes)
            )
            path: Path = Path(d=self.line.get_path(parallel_offset))
            style: dict[str, Any] = {
                "fill": "none",
                "stroke": color.hex,
                "stroke-linejoin": "round",
                "stroke-width": 1,
                "opacity": 0.5,
            }
            path.update(style)
            svg.add(path)

    def draw_caption(self, svg: Drawing) -> None:
        """Draw road name along its path."""
        name: Optional[str] = self.tags.get("name")
        if not name:
            return

        path: Path = svg.path(d=self.line.get_path(3), fill="none")
        svg.add(path)

        text = svg.add(svg.text.Text(""))
        text_path = svg.text.TextPath(
            path=path,
            text=name,
            startOffset=None,
            method="align",
            spacing="exact",
            font_family="Roboto",
            font_size=10,
        )
        text.add(text_path)


def get_curve_points(
    road: Road, scale: float, center: np.ndarray, road_end: np.ndarray
) -> list[np.ndarray]:
    """
    :param road: road segment
    :param scale: current zoom scale
    :param center: road intersection point
    :param road_end: end point of the road segment
    """
    width: float = road.width / 2.0 * scale

    direction: np.ndarray = (road_end - center) / np.linalg.norm(
        road_end - center
    )
    left: np.ndarray = turn_by_angle(direction, np.pi / 2.0) * width
    right: np.ndarray = turn_by_angle(direction, -np.pi / 2.0) * width

    return [road_end + left, center + left, center + right, road_end + right]


class Connector:
    """
    Two roads connection.
    """

    def __init__(
        self,
        connections: list[tuple[Road, int]],
        flinger: Flinger,
        scale: float,
    ) -> None:
        self.connections: list[tuple[Road, int]] = connections
        self.road_1: Road
        self.index_1: int
        self.road_1, self.index_1 = connections[0]
        self.priority = self.road_1.matcher.priority

        self.min_layer: float = min(x[0].layer for x in connections)
        self.max_layer: float = max(x[0].layer for x in connections)
        self.scale: float = scale
        self.flinger: Flinger = flinger

    def draw(self, svg: Drawing) -> None:
        """Draw connection fill."""
        raise NotImplementedError

    def draw_border(self, svg: Drawing) -> None:
        """Draw connection outline."""
        raise NotImplementedError


class SimpleConnector(Connector):
    """
    Simple connection between roads that don't change width.
    """

    def __init__(
        self,
        connections: list[tuple[Road, int]],
        flinger: Flinger,
        scale: float,
    ) -> None:
        super().__init__(connections, flinger, scale)

        self.road_2: Road = connections[1][0]
        self.index_2: int = connections[1][1]

        node: OSMNode = self.road_1.nodes[self.index_1]
        self.point: np.ndarray = flinger.fling(node.coordinates)

    def draw(self, svg: Drawing) -> None:
        """Draw connection fill."""
        circle: Circle = svg.circle(
            self.point,
            self.road_1.width * self.scale / 2,
            fill=self.road_1.get_color().hex,
        )
        svg.add(circle)

    def draw_border(self, svg: Drawing) -> None:
        """Draw connection outline."""
        circle: Circle = svg.circle(
            self.point,
            self.road_1.width * self.scale / 2 + 1,
            fill=self.road_1.matcher.border_color.hex,
        )
        svg.add(circle)


class ComplexConnector(Connector):
    """
    Connection between two roads that change width.
    """

    def __init__(
        self,
        connections: list[tuple[Road, int]],
        flinger: Flinger,
        scale: float,
    ) -> None:
        super().__init__(connections, flinger, scale)

        self.road_2: Road = connections[1][0]
        self.index_2: int = connections[1][1]

        length: float = abs(self.road_2.width - self.road_1.width) * scale
        self.road_1.line.shorten(self.index_1, length)
        self.road_2.line.shorten(self.index_2, length)

        node: OSMNode = self.road_1.nodes[self.index_1]
        point: np.ndarray = flinger.fling(node.coordinates)

        points_1: list[np.ndarray] = get_curve_points(
            self.road_1, scale, point, self.road_1.line.points[self.index_1]
        )
        points_2: list[np.ndarray] = get_curve_points(
            self.road_2, scale, point, self.road_2.line.points[self.index_2]
        )
        # fmt: off
        self.curve_1: PathCommands = [
            points_1[0], "C", points_1[1], points_2[2], points_2[3]
        ]
        self.curve_2: PathCommands = [
            points_2[0], "C", points_2[1], points_1[2], points_1[3]
        ]
        # fmt: on

    def draw(self, svg: Drawing) -> None:
        """Draw connection fill."""
        for road, index in [
            (self.road_1, self.index_1),
            (self.road_2, self.index_2),
        ]:
            circle: Circle = svg.circle(
                road.line.points[index],
                road.width * self.scale / 2,
                fill=road.get_color(),
            )
            svg.add(circle)

        path: Path = svg.path(
            d=["M"] + self.curve_1 + ["L"] + self.curve_2 + ["Z"],
            fill=self.road_1.get_color(),
        )
        svg.add(path)

    def draw_border(self, svg: Drawing) -> None:
        """Draw connection outline."""
        filter_: Filter = self.road_1.get_filter(svg, True)

        if filter_:
            path: Path = svg.path(
                d=["M"] + self.curve_1 + ["L"] + self.curve_2 + ["Z"],
                filter=filter_.get_funciri(),
            )
        else:
            path: Path = svg.path(
                d=["M"] + self.curve_1 + ["L"] + self.curve_2 + ["Z"]
            )
        path.update(self.road_1.get_style(self.flinger, True, True))
        svg.add(path)


class SimpleIntersection(Connector):
    """
    Connection between more than two roads.
    """

    def __init__(
        self,
        connections: list[tuple[Road, int]],
        flinger: Flinger,
        scale: float,
    ) -> None:
        super().__init__(connections, flinger, scale)

    def draw(self, svg: Drawing) -> None:
        """Draw connection fill."""
        for road, index in sorted(
            self.connections, key=lambda x: x[0].matcher.priority
        ):
            node: OSMNode = self.road_1.nodes[self.index_1]
            point: np.ndarray = self.flinger.fling(node.coordinates)
            circle: Circle = svg.circle(
                point, road.width * self.scale / 2, fill=road.matcher.color.hex
            )
            svg.add(circle)

    def draw_border(self, svg: Drawing) -> None:
        """Draw connection outline."""
        for road, index in self.connections:
            node: OSMNode = self.road_1.nodes[self.index_1]
            point: np.ndarray = self.flinger.fling(node.coordinates)
            circle: Circle = svg.circle(
                point,
                road.width * self.scale / 2 + 1,
                fill=road.matcher.border_color.hex,
            )
            svg.add(circle)


class Roads:
    """
    Whole road structure.
    """

    def __init__(self) -> None:
        self.roads: list[Road] = []
        self.nodes: dict[int, list[tuple[Road, int]]] = {}

    def append(self, road: Road) -> None:
        """Add road and update connections."""
        self.roads.append(road)
        for index, node in enumerate(road.nodes):
            if node.id_ not in self.nodes:
                self.nodes[node.id_] = []
            self.nodes[node.id_].append((road, index))

    def draw(
        self, svg: Drawing, flinger: Flinger, draw_captions: bool = False
    ) -> None:
        """Draw whole road system."""
        if not self.roads:
            return

        scale: float = flinger.get_scale(self.roads[0].nodes[0].coordinates)
        layered_roads: dict[float, list[Road]] = {}
        layered_connectors: dict[float, list[Connector]] = {}

        for road in self.roads:
            if road.layer not in layered_roads:
                layered_roads[road.layer] = []
            layered_roads[road.layer].append(road)

        for id_ in self.nodes:
            connected: list[tuple[Road, int]] = self.nodes[id_]
            connector: Connector

            if len(self.nodes[id_]) <= 1:
                continue
            elif len(self.nodes[id_]) == 2:
                road_1, index_1 = connected[0]
                road_2, index_2 = connected[1]
                if (
                    road_1.width == road_2.width
                    or index_1 not in [0, len(road_1.nodes) - 1]
                    or index_2 not in [0, len(road_2.nodes) - 1]
                ):
                    connector = SimpleConnector(connected, flinger, scale)
                else:
                    connector = ComplexConnector(connected, flinger, scale)
            else:
                continue
                # connector = SimpleIntersection(connected, flinger, scale)

            if connector.min_layer not in layered_connectors:
                layered_connectors[connector.min_layer] = []
            layered_connectors[connector.min_layer].append(connector)

            if connector.max_layer not in layered_connectors:
                layered_connectors[connector.max_layer] = []
            layered_connectors[connector.max_layer].append(connector)

        for layer in sorted(layered_roads.keys()):
            roads: list[Road] = sorted(
                layered_roads[layer], key=lambda x: x.matcher.priority
            )
            connectors: list[Connector]
            if layer in layered_connectors:
                connectors = layered_connectors[layer]
            else:
                connectors = []

            for road in roads:
                road.draw(svg, flinger, True)
            for connector in connectors:
                if connector.min_layer == layer:
                    connector.draw_border(svg)

            for road in roads:
                road.draw(svg, flinger, False)
            for connector in connectors:
                if connector.max_layer == layer:
                    connector.draw(svg)

            for road in roads:
                road.draw_lanes(svg, flinger, road.matcher.border_color)

        if draw_captions:
            for road in self.roads:
                road.draw_caption(svg)
