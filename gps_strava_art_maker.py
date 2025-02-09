#!/usr/bin/env python
import json
import sys
import os
import copy
import math
import folium
import geopy.distance
from PyQt5.QtCore import Qt, QUrl, QTimer
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QFileDialog,
    QLabel,
    QHBoxLayout,
    QSlider,
    QLineEdit,
)
from app.svg_gpx_manager import SvgGpxManager
from app.mpl_canvas import MplCanvas
from app.resizable_pane import ResizablePane, PaneManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GPS Strava Art Maker")
        self.manager = SvgGpxManager()
        self.svg_paths = None
        self.gpx_data = None
        self.original_gpx_data = None  # store original GPX to re-scale later
        self.project_path = os.getcwd()
        self.plot_canvas = MplCanvas(self, width=5, height=4, dpi=100)
        self.map_view = QWebEngineView()
        self.init_ui()
        self.update_map_view(self.map_view, self.gpx_data, self.project_path)

        # For demonstration, try loading a default SVG.
        self.load_svg("drawing.svg")

        # Start a timer to poll for marker dragend updates.
        self.markerUpdateTimer = QTimer(self)
        self.markerUpdateTimer.setInterval(500)  # every 500 ms
        self.markerUpdateTimer.timeout.connect(self.poll_marker_drag_end)
        self.markerUpdateTimer.start()

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignTop)

        # File loading buttons.
        file_layout = QHBoxLayout()
        self.load_svg_button = QPushButton("Load SVG")
        self.load_svg_button.clicked.connect(lambda: self.load_svg())
        file_layout.addWidget(self.load_svg_button)
        self.load_gpx_button = QPushButton("Load GPX")
        self.load_gpx_button.clicked.connect(lambda: self.load_gpx())
        file_layout.addWidget(self.load_gpx_button)
        main_layout.addLayout(file_layout)

        # Action buttons.
        action_layout = QHBoxLayout()
        self.reload_display_button = QPushButton("Reload Display")
        self.reload_display_button.clicked.connect(self.reload_display)
        action_layout.addWidget(self.reload_display_button)
        self.save_button = QPushButton("Save GPX")
        self.save_button.clicked.connect(self.save_gpx)
        action_layout.addWidget(self.save_button)
        main_layout.addLayout(action_layout)

        # Add path length label, input box, slider, and new button.
        slider_layout = QHBoxLayout()
        # Label for the path length inside a styled box similar to buttons.
        self.path_length_label = QLabel("Path Length (km)")
        self.path_length_label.setStyleSheet(
            "font-size: 20px; padding: 12px 20px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        slider_layout.addWidget(self.path_length_label)

        # Input box for the target path length (in km).
        self.path_length_input = QLineEdit("1.00")
        self.path_length_input.setPlaceholderText("Length (km):")
        self.path_length_input.setStyleSheet(
            "font-size: 20px; padding: 12px 20px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        self.path_length_input.setFixedWidth(100)
        self.path_length_input.editingFinished.connect(self.update_path_length_from_input)
        slider_layout.addWidget(self.path_length_input)

        # Create the slider.
        self.path_length_slider = QSlider(Qt.Horizontal)
        self.path_length_slider.setMinimum(0)
        self.path_length_slider.setMaximum(300)
        self.path_length_slider.setValue(100)  # initial value corresponding to 1 km.
        self.path_length_slider.valueChanged.connect(self.update_path_length_from_slider)
        slider_layout.addWidget(self.path_length_slider)

        # New button: "Move Path to Center"
        self.move_path_button = QPushButton("Move Path to Center")
        self.move_path_button.setStyleSheet(
            "font-size: 20px; padding: 12px 20px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        self.move_path_button.clicked.connect(self.move_path_to_center)
        slider_layout.addWidget(self.move_path_button)

        main_layout.addLayout(slider_layout)

        # Panes.
        self.plot_pane = ResizablePane("Plot", self.plot_canvas, "plot")
        self.map_pane = ResizablePane("Map", self.map_view, "map")
        self.splitter = PaneManager(Qt.Vertical, [self.plot_pane, self.map_pane])
        self.splitter.setSizes([500, 500])
        main_layout.addWidget(self.splitter)

        self.status_label = QLabel("Status: Ready")
        main_layout.addWidget(self.status_label)
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        self.apply_gui_styles()

    def apply_gui_styles(self):
        try:
            with open("style/modern_style.qss", "r") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Could not load style file: {e}")

    def load_svg(self, file_name=None):
        if not file_name:
            file_name, _ = QFileDialog.getOpenFileName(
                self, "Open SVG File", self.project_path, "SVG Files (*.svg)"
            )
        if file_name:
            try:
                self.svg_paths, self.gpx_data = self.manager.process_svg_file(file_name)
                self.original_gpx_data = copy.deepcopy(self.gpx_data)
                self.status_label.setText(f"Loaded SVG: {file_name}")
                self.update_slider_from_gpx()  # Recalculate path length and update slider.
                self.reload_display()
            except Exception as e:
                self.status_label.setText(f"Error loading SVG: {e}")

    def load_gpx(self, file_name=None):
        if not file_name:
            file_name, _ = QFileDialog.getOpenFileName(
                self, "Open GPX File", self.project_path, "GPX Files (*.gpx)"
            )
        if file_name:
            try:
                self.gpx_data = self.manager.load_gpx(file_name)
                self.original_gpx_data = copy.deepcopy(self.gpx_data)
                self.svg_paths = None
                self.status_label.setText(f"Loaded GPX: {file_name}")
                self.update_slider_from_gpx()  # Recalculate path length and update slider.
                self.reload_display()
            except Exception as e:
                self.status_label.setText(f"Error loading GPX: {e}")

    def update_slider_from_gpx(self):
        """Recalculate the actual path length and update the input box and slider."""
        if self.original_gpx_data is None:
            return
        actual_length = self.calculate_gpx_length(self.original_gpx_data)
        if actual_length <= 0:
            return
        km_val = actual_length / 1000.0
        # Calculate the slider value from the logarithmic mapping:
        # target_length = (10^(exponent))*1000, so exponent = log10(actual_length/1000)
        exponent = math.log10(actual_length / 1000.0)
        slider_value = int((exponent + 1) * 100)
        self.path_length_input.blockSignals(True)
        self.path_length_input.setText(f"{km_val:.2f}")
        self.path_length_input.blockSignals(False)
        self.path_length_slider.blockSignals(True)
        self.path_length_slider.setValue(slider_value)
        self.path_length_slider.blockSignals(False)

    def update_map_view(self, map_view, gpx_data, project_path):
        if gpx_data is None:
            default_lat, default_lon = 54.9048217, 23.9592468
            m = folium.Map(location=[default_lat, default_lon], zoom_start=14)
        else:
            coords = []
            for track in gpx_data.tracks:
                for segment in track.segments:
                    for point in segment.points:
                        coords.append([point.latitude, point.longitude])
            if not coords:
                m = folium.Map(location=[54.9048217, 23.9592468], zoom_start=14)
            else:
                center_lat = sum(lat for lat, lon in coords) / len(coords)
                center_lon = sum(lon for lat, lon in coords) / len(coords)
                m = folium.Map(location=[center_lat, center_lon], zoom_start=16)
                # (Optional) Load the draggable path plugin.
                m.get_root().html.add_child(
                    folium.Element('<script src="https://unpkg.com/leaflet-path-drag@0.0.8/Path.Drag.js"></script>')
                )
                # Convert coordinates list to JSON.
                coords_json = json.dumps(coords)
                # The handle is now positioned at the top edge (north) of the polyline bounds,
                # horizontally centered.
                script = f"""
                <script>
                document.addEventListener("DOMContentLoaded", function() {{
                    var map = {m.get_name()};
                    window.map = map;  // Expose map globally so that other JS calls can use it.
                    var coords = {coords_json};
                    // Create the polyline.
                    var gpxPolyline = L.polyline(coords, {{
                        color: 'red',
                        weight: 2.5,
                        opacity: 1
                    }}).addTo(map);
  
                    // Draw a bounding rectangle around the polyline.
                    var rect = L.rectangle(gpxPolyline.getBounds(), {{
                        color: 'blue',
                        weight: 1,
                        dashArray: '5,5',
                        fillOpacity: 0.0
                    }}).addTo(map);
  
                    // Compute handle position: horizontally centered, top (north) of bounds.
                    var bounds = gpxPolyline.getBounds();
                    var handlePos = L.latLng(bounds.getNorth(), (bounds.getWest() + bounds.getEast()) / 2);
                    var handle = L.marker(handlePos, {{
                        draggable: true
                    }}).addTo(map);
  
                    // Expose the polyline globally so Python can fetch its coordinates.
                    window.gpxPolyline = gpxPolyline;
  
                    // Reset marker drag flag.
                    window.markerDragEnded = false;
  
                    var handleStartPos;
                    var originalCoords;
  
                    handle.on('dragstart', function(e) {{
                        handleStartPos = e.target.getLatLng();
                        originalCoords = gpxPolyline.getLatLngs().map(function(latlng) {{
                            return [latlng.lat, latlng.lng];
                        }});
                    }});
  
                    handle.on('drag', function(e) {{
                        var newPos = e.target.getLatLng();
                        var latOffset = newPos.lat - handleStartPos.lat;
                        var lngOffset = newPos.lng - handleStartPos.lng;
                        var newCoords = originalCoords.map(function(coord) {{
                            return [coord[0] + latOffset, coord[1] + lngOffset];
                        }});
                        gpxPolyline.setLatLngs(newCoords);
                        rect.setBounds(gpxPolyline.getBounds());
                    }});
  
                    handle.on('dragend', function(e) {{
                        // Reposition handle to remain horizontally centered at the top edge.
                        var newBounds = gpxPolyline.getBounds();
                        var newHandlePos = L.latLng(newBounds.getNorth(), (newBounds.getWest() + newBounds.getEast()) / 2);
                        handle.setLatLng(newHandlePos);
                        window.markerDragEnded = true;  // set flag so Python can update GPX data
                    }});
                }});
                </script>
                """
                m.get_root().html.add_child(folium.Element(script))
        temp_file = os.path.join(project_path, "temp_map.html")
        m.save(temp_file)
        map_view.load(QUrl.fromLocalFile(temp_file))

    def reload_display(self):
        if self.gpx_data is None:
            self.status_label.setText("No GPX data to display. Load an SVG or GPX file first.")
            return
        self.plot_canvas.figure.clf()
        if self.svg_paths is not None:
            ax1 = self.plot_canvas.figure.add_subplot(121)
            ax2 = self.plot_canvas.figure.add_subplot(122)
            self.manager.plot_svg(self.svg_paths, ax1)
            self.manager.plot_gpx(self.gpx_data, ax2)
            ax1.set_title("SVG Path")
            ax2.set_title("GPX Path")
            ax1.set_aspect("equal", "box")
            ax2.set_aspect("equal", "box")
        else:
            ax = self.plot_canvas.figure.add_subplot(111)
            self.manager.plot_gpx(self.gpx_data, ax)
            ax.set_title("GPX Path")
            ax.set_aspect("equal", "box")
        self.plot_canvas.figure.tight_layout()
        self.plot_canvas.draw()
        self.update_map_view(self.map_view, self.gpx_data, self.project_path)

    def save_gpx(self):
        if self.gpx_data is None:
            self.status_label.setText("No GPX data to save. Load an SVG or GPX file first.")
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save GPX File", self.project_path, "GPX Files (*.gpx);;All Files (*)"
        )
        if save_path:
            try:
                with open(save_path, "w") as f:
                    f.write(self.gpx_data.to_xml())
                self.status_label.setText(f"GPX file saved to: {save_path}")
            except Exception as e:
                self.status_label.setText(f"Error saving GPX: {e}")

    def calculate_gpx_length(self, gpx):
        """Calculate the total length of the GPX path in meters."""
        total_length = 0.0
        for track in gpx.tracks:
            for segment in track.segments:
                pts = segment.points
                for i in range(1, len(pts)):
                    p1 = pts[i - 1]
                    p2 = pts[i]
                    total_length += geopy.distance.distance(
                        (p1.latitude, p1.longitude), (p2.latitude, p2.longitude)
                    ).meters
        return total_length

    def scale_gpx_path(self, gpx, scale_factor):
        """
        Return a new GPX object with all points scaled relative to the centroid.
        Resizing uniformly scales the path length by the same factor.
        """
        new_gpx = copy.deepcopy(gpx)
        lat_sum, lon_sum, count = 0.0, 0.0, 0
        for track in new_gpx.tracks:
            for segment in track.segments:
                for p in segment.points:
                    lat_sum += p.latitude
                    lon_sum += p.longitude
                    count += 1
        if count == 0:
            return new_gpx
        center_lat = lat_sum / count
        center_lon = lon_sum / count
        for track in new_gpx.tracks:
            for segment in track.segments:
                for p in segment.points:
                    p.latitude = center_lat + scale_factor * (p.latitude - center_lat)
                    p.longitude = center_lon + scale_factor * (p.longitude - center_lon)
        return new_gpx

    def translate_gpx_path(self, gpx, lat_offset, lng_offset):
        """Return a new GPX object with all points translated by the given offsets."""
        new_gpx = copy.deepcopy(gpx)
        for track in new_gpx.tracks:
            for segment in track.segments:
                for p in segment.points:
                    p.latitude += lat_offset
                    p.longitude += lng_offset
        return new_gpx

    def format_distance(self, meters):
        """Format the distance in meters as a human‑readable string."""
        if meters >= 1000:
            return f"{meters/1000:.2f} km"
        else:
            return f"{meters:.0f} m"

    def update_path_length_from_slider(self):
        slider_value = self.path_length_slider.value()
        exponent = slider_value / 100 - 1
        target_length = (10 ** exponent) * 1000  # in meters
        km_val = target_length / 1000.0
        self.path_length_input.blockSignals(True)
        self.path_length_input.setText(f"{km_val:.2f}")
        self.path_length_input.blockSignals(False)
        if self.original_gpx_data is None:
            return
        original_length = self.calculate_gpx_length(self.original_gpx_data)
        if original_length == 0:
            return
        scale_factor = target_length / original_length
        self.gpx_data = self.scale_gpx_path(self.original_gpx_data, scale_factor)
        self.reload_display()

    def update_path_length_from_input(self):
        text = self.path_length_input.text()
        try:
            km_val = float(text)
        except ValueError:
            return
        target_length = km_val * 1000.0
        if target_length <= 0:
            return
        exponent = math.log10(target_length / 1000.0)
        slider_value = int((exponent + 1) * 100)
        self.path_length_slider.blockSignals(True)
        self.path_length_slider.setValue(slider_value)
        self.path_length_slider.blockSignals(False)
        if self.original_gpx_data is None:
            return
        original_length = self.calculate_gpx_length(self.original_gpx_data)
        if original_length == 0:
            return
        scale_factor = target_length / original_length
        self.gpx_data = self.scale_gpx_path(self.original_gpx_data, scale_factor)
        self.reload_display()

    def move_path_to_center(self):
        # First, update the gpx_data from the JS polyline.
        self.map_view.page().runJavaScript("JSON.stringify(window.gpxPolyline.getLatLngs())", self._move_path_to_center_after_js)

    def _move_path_to_center_after_js(self, js_result):
        print("_move_path_to_center_after_js")
        try:
            coords_list = json.loads(js_result)
        except Exception as e:
            coords_list = None
            print("Error parsing JS result:", e)
        if coords_list is not None:
            i = 0
            for track in self.gpx_data.tracks:
                for segment in track.segments:
                    for p in segment.points:
                        if i < len(coords_list):
                            p.latitude = coords_list[i]["lat"]
                            p.longitude = coords_list[i]["lng"]
                            i += 1
            print("After move button, GPX coordinates:")
            for track in self.gpx_data.tracks:
                for segment in track.segments:
                    for p in segment.points:
                        print(f"({p.latitude}, {p.longitude})")
        self.map_view.page().runJavaScript("map.getCenter()", self.handle_map_center)

    def handle_map_center(self, center):
        if not center:
            return
        coords = []
        for track in self.gpx_data.tracks:
            for segment in track.segments:
                for p in segment.points:
                    coords.append([p.latitude, p.longitude])
        if not coords:
            return
        poly_center_lat = sum(c[0] for c in coords) / len(coords)
        poly_center_lng = sum(c[1] for c in coords) / len(coords)
        lat_offset = center["lat"] - poly_center_lat
        lng_offset = center["lng"] - poly_center_lng
        self.gpx_data = self.translate_gpx_path(self.gpx_data, lat_offset, lng_offset)
        self.original_gpx_data = copy.deepcopy(self.gpx_data)
        print("handle_map_center center, lat_offset, lng_offset", center, lat_offset, lng_offset)
        print("After move to center, updated GPX coordinates:")
        for track in self.gpx_data.tracks:
            for segment in track.segments:
                for p in segment.points:
                    print(f"({p.latitude}, {p.longitude})")
        self.reload_display()

    def poll_marker_drag_end(self):
        # Poll for the global flag set by the JS dragend event.
        self.map_view.page().runJavaScript("window.markerDragEnded", self._handle_marker_drag_end)

    def _handle_marker_drag_end(self, dragEnded):
        if dragEnded:
            # If the marker drag has ended, update GPX data from the JS polyline.
            self.map_view.page().runJavaScript("JSON.stringify(window.gpxPolyline.getLatLngs())", self._update_gpx_from_marker)
            # Reset the flag in JS.
            self.map_view.page().runJavaScript("window.markerDragEnded = false;")

    def _update_gpx_from_marker(self, js_result):
        print("_update_gpx_from_marker")
        try:
            coords_list = json.loads(js_result)
        except Exception as e:
            coords_list = None
            print("Error parsing JS result in _update_gpx_from_marker:", e)
        if coords_list is not None:
            i = 0
            for track in self.gpx_data.tracks:
                for segment in track.segments:
                    for p in segment.points:
                        if i < len(coords_list):
                            p.latitude = coords_list[i]["lat"]
                            p.longitude = coords_list[i]["lng"]
                            i += 1
            print("After marker drag, updated GPX coordinates:")
            for track in self.gpx_data.tracks:
                for segment in track.segments:
                    for p in segment.points:
                        print(f"({p.latitude}, {p.longitude})")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1000, 800)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
