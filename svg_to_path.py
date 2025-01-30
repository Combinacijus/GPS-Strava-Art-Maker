import sys
import os
import numpy as np
import matplotlib.pyplot as plt
import gpxpy
import gpxpy.gpx
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QFileDialog
from PyQt5.QtCore import QStandardPaths
from svgpathtools import svg2paths, Path, Line, CubicBezier, QuadraticBezier
from geopy.distance import geodesic


class SvgViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.INTERPOLATION_POINTS = 3
        self.LAT = 54.899
        self.LON = 23.9
        self.file_name = "drawing.svg"
        self.svg_paths = None
        self.gpx_data = None
        
        self.init_ui()
        self.load_svg(self.file_name, show=False)
        self.svg_paths, self.gpx_data = self.get_svg_and_gpx(self.file_name)
        self.save_gpx(self.file_name.split(".")[0] + ".gpx")
        self.display_svg_and_gpx(self.svg_paths, self.gpx_data)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        load_button = QPushButton("Load SVG")
        load_button.clicked.connect(self.load_svg)
        layout.addWidget(load_button)
        
        save_button = QPushButton("Save GPX")
        save_button.clicked.connect(self.save_gpx)
        layout.addWidget(save_button)
        
        self.setLayout(layout)

    def load_svg(self, file_name=None, show=True):
        if not file_name:
            downloads_path = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
            file_name, _ = QFileDialog.getOpenFileName(self, "Open SVG File", downloads_path, "SVG Files (*.svg)")
            
        if file_name:
            self.file_name = file_name
            if show:
                self.svg_paths, self.gpx_data = self.get_svg_and_gpx(file_name)
                self.display_svg_and_gpx(self.svg_paths, self.gpx_data)

    def get_svg_and_gpx(self, file_name):
        if not os.path.exists(file_name):
            print("File not found:", file_name)
            return None, None
        
        svg_paths, _ = svg2paths(file_name)
        gpx_data = self.convert_svg_to_gpx(svg_paths)
        gpx_data = self.scale_gpx(gpx_data, 500)
        gpx_data = self.center_gpx_at(gpx_data, self.LAT, self.LON)
        
        return svg_paths, gpx_data

    def display_svg_and_gpx(self, svg_paths, gpx):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 12))
        self.plot_svg(svg_paths, ax1)
        ax1.set_title("SVG Path")
        ax1.set_aspect('equal', 'box')
        self.plot_gpx(gpx, ax2)
        ax2.set_title("GPX Path")
        ax2.set_aspect('equal', 'box')
        plt.tight_layout()
        plt.show()

    def plot_svg(self, paths, ax):
        for path in paths:
            for segment in path:
                if isinstance(segment, Line):
                    x = [segment.start.real, segment.end.real]
                    y = [-segment.start.imag, -segment.end.imag]  # Flip y for SVG
                    ax.plot(x, y, 'b-', lw=1)
                    ax.plot([segment.start.real, segment.end.real], [-segment.start.imag, -segment.end.imag], 'ko')

                elif isinstance(segment, (CubicBezier, QuadraticBezier)):
                    self.plot_bezier_curve(segment, ax)

    def plot_bezier_curve(self, segment, ax):
        t_vals = np.linspace(0, 1, 100)
        if isinstance(segment, CubicBezier):
            x_vals, y_vals = self.calculate_cubic_bezier(segment, t_vals)
        else:  # Quadratic Bezier
            x_vals, y_vals = self.calculate_quadratic_bezier(segment, t_vals)
        
        ax.plot(x_vals, -y_vals, 'b-', lw=1)  # Flip y for SVG
        ax.plot([segment.start.real, segment.end.real], [-segment.start.imag, -segment.end.imag], 'ko')

    def calculate_cubic_bezier(self, segment, t_vals):
        x_vals = (1 - t_vals)**3 * segment.start.real + 3 * (1 - t_vals)**2 * t_vals * segment.control1.real + \
                 3 * (1 - t_vals) * t_vals**2 * segment.control2.real + t_vals**3 * segment.end.real
        y_vals = (1 - t_vals)**3 * segment.start.imag + 3 * (1 - t_vals)**2 * t_vals * segment.control1.imag + \
                 3 * (1 - t_vals) * t_vals**2 * segment.control2.imag + t_vals**3 * segment.end.imag
        return x_vals, y_vals

    def calculate_quadratic_bezier(self, segment, t_vals):
        x_vals = (1 - t_vals)**2 * segment.start.real + 2 * (1 - t_vals) * t_vals * segment.control.real + \
                 t_vals**2 * segment.end.real
        y_vals = (1 - t_vals)**2 * segment.start.imag + 2 * (1 - t_vals) * t_vals * segment.control.imag + \
                 t_vals**2 * segment.end.imag
        return x_vals, y_vals

    def plot_gpx(self, gpx, ax):
        for track in gpx.tracks:
            for segment in track.segments:
                x_vals = [point.latitude for point in segment.points]  
                y_vals = [point.longitude for point in segment.points]  
                ax.plot(y_vals, x_vals, 'ro-', lw=2, label="GPX Path")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")

    def convert_svg_to_gpx(self, paths):
        gpx = gpxpy.gpx.GPX()
        track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(track)
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        track.segments.append(gpx_segment)

        for path in paths:
            for path_segment in path:
                if isinstance(path_segment, Line):
                    self.process_line(path_segment, gpx_segment)
                elif isinstance(path_segment, (CubicBezier, QuadraticBezier)):
                    self.process_bezier(path_segment, gpx_segment)

        return gpx

    def process_line(self, path_segment, gpx_segment):
        segment_points = [(path_segment.start.real, path_segment.start.imag), (path_segment.end.real, path_segment.end.imag)]
        for point in segment_points:
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(-point[1], point[0]))  # Flip y for GPX

    def process_bezier(self, path_segment, gpx_segment):
        t_vals = np.linspace(0, 1, self.INTERPOLATION_POINTS)
        if isinstance(path_segment, CubicBezier):
            x_vals, y_vals = self.calculate_cubic_bezier(path_segment, t_vals)
        else:  # Quadratic Bezier
            x_vals, y_vals = self.calculate_quadratic_bezier(path_segment, t_vals)

        for x, y in zip(x_vals, y_vals):
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(-y, x))  # Flip y for GPX

    def center_gpx_at(self, gpx, lat, lon):
        latitudes = [point.latitude for track in gpx.tracks for segment in track.segments for point in segment.points]
        longitudes = [point.longitude for track in gpx.tracks for segment in track.segments for point in segment.points]
        current_center_lat = np.mean(latitudes)
        current_center_lon = np.mean(longitudes)

        lat_offset = lat - current_center_lat
        lon_offset = lon - current_center_lon

        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    point.latitude += lat_offset
                    point.longitude += lon_offset
                    
        return gpx

    def scale_gpx(self, gpx, target_size_meters):
        scale_down_factor = 0.000001  # Lat and Lon must be in range of [-90..90]
                
        latitudes = [point.latitude for track in gpx.tracks for segment in track.segments for point in segment.points]
        longitudes = [point.longitude for track in gpx.tracks for segment in track.segments for point in segment.points]
        
        min_lat = min(latitudes) * scale_down_factor
        max_lat = max(latitudes) * scale_down_factor
        min_lon = min(longitudes) * scale_down_factor
        max_lon = max(longitudes) * scale_down_factor
        
        height = geodesic((min_lat, min_lon), (max_lat, min_lon)).meters
        width = geodesic((min_lat, min_lon), (min_lat, max_lon)).meters
        largest_dimension = max(height, width)
        scale_factor = target_size_meters / largest_dimension * scale_down_factor

        new_gpx = gpxpy.gpx.GPX()
        track = gpxpy.gpx.GPXTrack()
        new_gpx.tracks.append(track)
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        track.segments.append(gpx_segment)

        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    lat_diff = point.latitude - min_lat
                    lon_diff = point.longitude - min_lon
                    scaled_lat = min_lat + lat_diff * scale_factor
                    scaled_lon = min_lon + lon_diff * scale_factor
                    gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(scaled_lat, scaled_lon))

        return new_gpx

    def save_gpx(self, save_path=None):
        if self.gpx_data:
            if not save_path:
                options = QFileDialog.Options()
                save_path, _ = QFileDialog.getSaveFileName(self, "Save GPX File", "", "GPX Files (*.gpx);;All Files (*)", options=options)
            
            if save_path:
                with open(save_path, "w") as f:
                    f.write(self.gpx_data.to_xml())
                print(f"GPX file saved to {save_path}")

def main():
    app = QApplication(sys.argv)
    viewer = SvgViewer()
    viewer.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
