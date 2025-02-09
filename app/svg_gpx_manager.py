import os
import numpy as np
import matplotlib.pyplot as plt
import gpxpy
import gpxpy.gpx
from svgpathtools import svg2paths, Line, CubicBezier, QuadraticBezier
from geopy.distance import geodesic


class SvgGpxManager:
    def __init__(self, target_size_meters=100, center_lat=54.904643, center_lon=23.957831, interpolation_points=3):
        self.target_size_meters = target_size_meters
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.interpolation_points = interpolation_points

    def load_svg(self, file_name):
        if not os.path.exists(file_name):
            raise FileNotFoundError(f"SVG file not found: {file_name}")
        svg_paths, _ = svg2paths(file_name)
        return svg_paths

    def convert_svg_to_gpx(self, svg_paths):
        gpx = gpxpy.gpx.GPX()
        track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(track)
        segment = gpxpy.gpx.GPXTrackSegment()
        track.segments.append(segment)

        for path in svg_paths:
            for seg in path:
                if isinstance(seg, Line):
                    self.process_line(seg, segment)
                elif isinstance(seg, (CubicBezier, QuadraticBezier)):
                    self.process_bezier(seg, segment)
        return gpx

    def process_line(self, seg, gpx_segment):
        points = [(seg.start.real, seg.start.imag), (seg.end.real, seg.end.imag)]
        for pt in points:
            # Flip y for GPX conversion
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(-pt[1], pt[0]))

    def process_bezier(self, seg, gpx_segment):
        t_vals = np.linspace(0, 1, self.interpolation_points)
        if isinstance(seg, CubicBezier):
            x_vals, y_vals = self.calculate_cubic_bezier(seg, t_vals)
        else:  # QuadraticBezier
            x_vals, y_vals = self.calculate_quadratic_bezier(seg, t_vals)
        for x, y in zip(x_vals, y_vals):
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(-y, x))

    def calculate_cubic_bezier(self, seg, t_vals):
        x_vals = ((1 - t_vals) ** 3 * seg.start.real +
                  3 * (1 - t_vals) ** 2 * t_vals * seg.control1.real +
                  3 * (1 - t_vals) * t_vals ** 2 * seg.control2.real +
                  t_vals ** 3 * seg.end.real)
        y_vals = ((1 - t_vals) ** 3 * seg.start.imag +
                  3 * (1 - t_vals) ** 2 * t_vals * seg.control1.imag +
                  3 * (1 - t_vals) * t_vals ** 2 * seg.control2.imag +
                  t_vals ** 3 * seg.end.imag)
        return x_vals, y_vals

    def calculate_quadratic_bezier(self, seg, t_vals):
        x_vals = ((1 - t_vals) ** 2 * seg.start.real +
                  2 * (1 - t_vals) * t_vals * seg.control.real +
                  t_vals ** 2 * seg.end.real)
        y_vals = ((1 - t_vals) ** 2 * seg.start.imag +
                  2 * (1 - t_vals) * t_vals * seg.control.imag +
                  t_vals ** 2 * seg.end.imag)
        return x_vals, y_vals

    def scale_gpx(self, gpx):
        scale_down_factor = 0.000001  # Adjust coordinate range
        latitudes = [p.latitude for track in gpx.tracks for seg in track.segments for p in seg.points]
        longitudes = [p.longitude for track in gpx.tracks for seg in track.segments for p in seg.points]
        min_lat = min(latitudes) * scale_down_factor
        max_lat = max(latitudes) * scale_down_factor
        min_lon = min(longitudes) * scale_down_factor
        max_lon = max(longitudes) * scale_down_factor

        height = geodesic((min_lat, min_lon), (max_lat, min_lon)).meters
        width = geodesic((min_lat, min_lon), (min_lat, max_lon)).meters
        largest_dimension = max(height, width)
        scale_factor = self.target_size_meters / largest_dimension * scale_down_factor

        new_gpx = gpxpy.gpx.GPX()
        track = gpxpy.gpx.GPXTrack()
        new_gpx.tracks.append(track)
        segment = gpxpy.gpx.GPXTrackSegment()
        track.segments.append(segment)

        for t in gpx.tracks:
            for seg in t.segments:
                for p in seg.points:
                    lat_diff = p.latitude - min_lat
                    lon_diff = p.longitude - min_lon
                    scaled_lat = min_lat + lat_diff * scale_factor
                    scaled_lon = min_lon + lon_diff * scale_factor
                    segment.points.append(gpxpy.gpx.GPXTrackPoint(scaled_lat, scaled_lon))
        return new_gpx

    def center_gpx_at(self, gpx):
        latitudes = [p.latitude for track in gpx.tracks for seg in track.segments for p in seg.points]
        longitudes = [p.longitude for track in gpx.tracks for seg in track.segments for p in seg.points]
        current_center_lat = np.mean(latitudes)
        current_center_lon = np.mean(longitudes)

        lat_offset = self.center_lat - current_center_lat
        lon_offset = self.center_lon - current_center_lon

        for track in gpx.tracks:
            for seg in track.segments:
                for p in seg.points:
                    p.latitude += lat_offset
                    p.longitude += lon_offset
        return gpx

    def process_svg_file(self, file_name):
        svg_paths = self.load_svg(file_name)
        gpx = self.convert_svg_to_gpx(svg_paths)
        gpx = self.scale_gpx(gpx)
        gpx = self.center_gpx_at(gpx)
        return svg_paths, gpx

    def load_gpx(self, file_name):
        if not os.path.exists(file_name):
            raise FileNotFoundError(f"GPX file not found: {file_name}")
        with open(file_name, "r") as f:
            gpx = gpxpy.parse(f)
        return gpx

    def display_svg_and_gpx(self, svg_paths, gpx):
        fig, (ax1, ax2) = plt.subplots(2, 1)
        self.plot_svg(svg_paths, ax1)
        ax1.set_title("SVG Path")
        ax1.set_aspect("equal", "box")
        self.plot_gpx(gpx, ax2)
        ax2.set_title("GPX Path")
        ax2.set_aspect("equal", "box")
        plt.tight_layout()
        plt.show()

    def display_gpx_only(self, gpx):
        fig, ax = plt.subplots()
        self.plot_gpx(gpx, ax)
        ax.set_title("GPX Path")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_aspect("equal", "box")
        plt.tight_layout()
        plt.show()

    def plot_svg(self, paths, ax):
        for path in paths:
            for seg in path:
                if isinstance(seg, Line):
                    x = [seg.start.real, seg.end.real]
                    y = [-seg.start.imag, -seg.end.imag]  # Flip y for display
                    ax.plot(x, y, "b-", lw=1)
                    ax.plot(x, y, "ko")
                elif isinstance(seg, (CubicBezier, QuadraticBezier)):
                    self.plot_bezier_curve(seg, ax)

    def plot_bezier_curve(self, seg, ax):
        t_vals = np.linspace(0, 1, 100)
        if isinstance(seg, CubicBezier):
            x_vals, y_vals = self.calculate_cubic_bezier(seg, t_vals)
        else:
            x_vals, y_vals = self.calculate_quadratic_bezier(seg, t_vals)
        ax.plot(x_vals, -y_vals, "b-", lw=1)  # Flip y for display
        ax.plot([seg.start.real, seg.end.real], [-seg.start.imag, -seg.end.imag], "ko")

    def plot_gpx(self, gpx, ax):
        for track in gpx.tracks:
            for seg in track.segments:
                lats = [p.latitude for p in seg.points]
                lons = [p.longitude for p in seg.points]
                ax.plot(lons, lats, "ro-", lw=2)
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
