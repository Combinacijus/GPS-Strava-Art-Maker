#!/usr/bin/env python
import json
import sys
import os
import copy
import math
import folium
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
        self.svg_gpx_manager = SvgGpxManager()
        self.svg_paths = None
        # original_gpx_data: uniform scaling (path length + marker updates)

        self.gpx_data_1_original = None
        self.gpx_data_2_scaled_translated = None
        self.gpx_data_3_final = None

        self.project_path = os.getcwd()
        self.plot_canvas = MplCanvas(self, width=5, height=4, dpi=100)
        self.map_view = QWebEngineView()

        # Additional transform parameters:
        self.rotation = 0  # degrees (applied after horizontal scaling)
        self.hor_scale = 1.0  # horizontal scaling factor (1.0 = 100%)

        self.init_ui()

        # For demonstration, try loading a default SVG.
        try:
            self.load_svg("drawing.svg")
        except Exception:
            pass

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
        self.reload_display_button.clicked.connect(self.reload_gui)
        action_layout.addWidget(self.reload_display_button)
        self.save_button = QPushButton("Save GPX")
        self.save_button.clicked.connect(self.save_gpx)
        action_layout.addWidget(self.save_button)
        main_layout.addLayout(action_layout)

        # ----- Path Length Controls (existing) -----
        slider_layout = QHBoxLayout()
        self.path_length_label = QLabel("Path Length (km)")
        self.path_length_label.setStyleSheet(
            "font-size: 20px; padding: 12px 20px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        slider_layout.addWidget(self.path_length_label)

        self.path_length_input = QLineEdit("1.00")
        self.path_length_input.setPlaceholderText("Length (km):")
        self.path_length_input.setStyleSheet(
            "font-size: 20px; padding: 12px 20px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        self.path_length_input.setFixedWidth(100)
        self.path_length_input.editingFinished.connect(self.update_path_length_from_input)
        slider_layout.addWidget(self.path_length_input)

        self.exponent_scale = 1000  # exp(x/exponent_scale)
        self.path_length_slider = QSlider(Qt.Horizontal)  # Log scale slider
        self.path_length_slider.setMinimum(0)
        self.path_length_slider.setMaximum(3 * self.exponent_scale)
        self.path_length_slider.setValue(1 * self.exponent_scale)  # default corresponding to ~1 km
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

        # ----- New Transformation Controls -----
        # Rotation control row
        rotation_layout = QHBoxLayout()
        self.rotation_label = QLabel("Rotation (deg)")
        self.rotation_label.setStyleSheet(
            "font-size: 20px; padding: 12px 20px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        rotation_layout.addWidget(self.rotation_label)

        self.rotation_input = QLineEdit("0")
        self.rotation_input.setPlaceholderText("0")
        self.rotation_input.setStyleSheet(
            "font-size: 20px; padding: 12px 20px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        self.rotation_input.setFixedWidth(100)
        self.rotation_input.editingFinished.connect(self.update_rotation_from_input)
        rotation_layout.addWidget(self.rotation_input)

        self.rotation_slider = QSlider(Qt.Horizontal)
        self.rotation_slider.setMinimum(-180)
        self.rotation_slider.setMaximum(180)
        self.rotation_slider.setValue(0)
        self.rotation_slider.valueChanged.connect(self.update_rotation_from_slider)
        rotation_layout.addWidget(self.rotation_slider)

        main_layout.addLayout(rotation_layout)

        # Horizontal scaling control row
        hor_scale_layout = QHBoxLayout()
        self.hor_scale_label = QLabel("Horizontal Scale (%)")
        self.hor_scale_label.setStyleSheet(
            "font-size: 20px; padding: 12px 20px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        hor_scale_layout.addWidget(self.hor_scale_label)

        self.hor_scale_input = QLineEdit("100")
        self.hor_scale_input.setPlaceholderText("100")
        self.hor_scale_input.setStyleSheet(
            "font-size: 20px; padding: 12px 20px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        self.hor_scale_input.setFixedWidth(100)
        self.hor_scale_input.editingFinished.connect(self.update_hor_scale_from_input)
        hor_scale_layout.addWidget(self.hor_scale_input)

        self.hor_scale_slider = QSlider(Qt.Horizontal)
        self.hor_scale_slider.setMinimum(50)  # 50% = 0.5
        self.hor_scale_slider.setMaximum(200)  # 200% = 2.0
        self.hor_scale_slider.setValue(100)  # default 100% = 1.0
        self.hor_scale_slider.valueChanged.connect(self.update_hor_scale_from_slider)
        hor_scale_layout.addWidget(self.hor_scale_slider)

        main_layout.addLayout(hor_scale_layout)

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
            file_name, _ = QFileDialog.getOpenFileName(self, "Open SVG File", self.project_path, "SVG Files (*.svg)")
        if file_name:
            try:
                self.svg_paths, self.gpx_data_1_original = self.svg_gpx_manager.process_svg_file(file_name)
                self.gpx_data_2_scaled_translated = copy.deepcopy(self.gpx_data_1_original)
                self.gpx_data_3_final = copy.deepcopy(self.gpx_data_1_original)
                self.status_label.setText(f"Loaded SVG: {file_name}")

                self.update_all_slider_from_gpx(self.gpx_data_1_original)
                self.update_final_gpx()
            except Exception as e:
                self.status_label.setText(f"Error loading SVG: {e}")

    def load_gpx(self, file_name=None):
        if not file_name:
            file_name, _ = QFileDialog.getOpenFileName(self, "Open GPX File", self.project_path, "GPX Files (*.gpx)")
        if file_name:
            try:
                self.gpx_data_1_original = self.svg_gpx_manager.load_gpx(file_name)
                self.gpx_data_2_scaled_translated = copy.deepcopy(self.gpx_data_1_original)
                self.gpx_data_3_final = copy.deepcopy(self.gpx_data_1_original)
                self.svg_paths = None
                self.status_label.setText(f"Loaded GPX: {file_name}")

                self.update_all_slider_from_gpx(self.gpx_data_1_original)
                self.update_final_gpx()
            except Exception as e:
                self.status_label.setText(f"Error loading GPX: {e}")

    def update_all_slider_from_gpx(self, gpx):
        self.rotation_slider.setValue(0)
        self.rotation_input.setPlaceholderText("0")
        self.hor_scale_slider.setValue(100)
        self.hor_scale_input.setPlaceholderText("100")

    def save_gpx(self):
        if self.gpx_data_3_final is None:
            self.status_label.setText("No GPX data to save. Load an SVG or GPX file first.")
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "Save GPX File", self.project_path, "GPX Files (*.gpx);;All Files (*)")
        if save_path:
            try:
                self.svg_gpx_manager.save_gpx(self.gpx_data_3_final, save_path)
                self.status_label.setText(f"GPX file saved to: {save_path}")
            except Exception as e:
                self.status_label.setText(f"Error saving GPX: {e}")

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
                m.get_root().html.add_child(folium.Element('<script src="https://unpkg.com/leaflet-path-drag@0.0.8/Path.Drag.js"></script>'))
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

        # temp_file = os.path.join(project_path, "temp_map.html")
        # m.save(temp_file)
        # map_view.load(QUrl.fromLocalFile(temp_file))

        map_html = m.get_root().render()
        map_view.setHtml(map_html)

    def reload_gui(self):
        if self.gpx_data_3_final is None:
            self.status_label.setText("No GPX data to display. Load an SVG or GPX file first.")
            return

        self.plot_canvas.figure.clf()

        if self.svg_paths is not None:
            ax1 = self.plot_canvas.figure.add_subplot(121)
            ax2 = self.plot_canvas.figure.add_subplot(122)
            self.svg_gpx_manager.plot_svg(self.svg_paths, ax1)
            self.svg_gpx_manager.plot_gpx(self.gpx_data_3_final, ax2)
            ax1.set_title("SVG Path")
            ax2.set_title("GPX Path")
            ax1.set_aspect("equal", "box")
            ax2.set_aspect("equal", "box")
        else:
            ax = self.plot_canvas.figure.add_subplot(111)
            self.svg_gpx_manager.plot_gpx(self.gpx_data_3_final, ax)
            ax.set_title("GPX Path")
            ax.set_aspect("equal", "box")

        self.plot_canvas.figure.tight_layout()
        self.plot_canvas.draw()

        self.update_map_view(self.map_view, self.gpx_data_3_final, self.project_path)

    def scale_gpx_path(self, gpx, scale_factor):
        center_lat, center_lon = self.svg_gpx_manager.get_path_center_lat_lon(gpx)
        if not center_lat or not center_lon:
            return gpx

        gpx_scaled = self.svg_gpx_manager.scale_gpx_around_point(gpx, center_lat, center_lon, scale_factor)

        return gpx_scaled

    def translate_gpx_path(self, gpx, lat_offset, lng_offset):
        new_gpx = copy.deepcopy(gpx)
        for track in new_gpx.tracks:
            for segment in track.segments:
                for p in segment.points:
                    p.latitude += lat_offset
                    p.longitude += lng_offset
        return new_gpx

    def gpx_transform_and_rotate(self, gpx):
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

        # Apply horizontal scaling (scale only the longitude relative to center)
        for track in new_gpx.tracks:
            for segment in track.segments:
                for p in segment.points:
                    p.longitude = center_lon + self.hor_scale * (p.longitude - center_lon)

        # Apply rotation around the centroid.
        angle_rad = -math.radians(self.rotation)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        for track in new_gpx.tracks:
            for segment in track.segments:
                for p in segment.points:
                    dlat = p.latitude - center_lat
                    dlon = p.longitude - center_lon
                    new_dlon = dlon * cos_a - dlat * sin_a
                    new_dlat = dlon * sin_a + dlat * cos_a
                    p.longitude = center_lon + new_dlon
                    p.latitude = center_lat + new_dlat

        return new_gpx

    def update_final_gpx(self):
        if self.gpx_data_2_scaled_translated is None:
            return

        gpx_data_transformed = self.gpx_transform_and_rotate(self.gpx_data_2_scaled_translated)
        self.gpx_data_3_final = self.fix_lat_lon_scaling(gpx_data_transformed)

        self.reload_gui()

    def len_km_to_slider(self, val_km):
        exponent = math.log10(val_km)
        return int((exponent + 1) * self.exponent_scale)

    def len_slider_to_km(self, slider_value):
        exponent = slider_value / self.exponent_scale - 1
        return 10**exponent

    def resize_to_target_path_length(self, target_length_km):
        """Helper method to update the path length, scale factor, and GPX data."""
        if target_length_km <= 0 or self.gpx_data_1_original is None:
            return

        original_length_km = self.svg_gpx_manager.calculate_gpx_length_km(self.gpx_data_1_original)
        if original_length_km == 0:
            return

        scale_factor = target_length_km / original_length_km
        self.gpx_data_2_scaled_translated = self.scale_gpx_path(self.gpx_data_1_original, scale_factor)
        self.update_final_gpx()

    def update_path_length_from_slider(self):
        slider_value = self.path_length_slider.value()

        target_length_km = self.len_slider_to_km(slider_value)

        self.path_length_input.blockSignals(True)
        self.path_length_input.setText(f"{target_length_km:.2f}")
        self.path_length_input.blockSignals(False)

        self.resize_to_target_path_length(target_length_km)

    def update_path_length_from_input(self):
        text = self.path_length_input.text()
        try:
            target_length_km = float(text)
        except ValueError:
            return

        print(f"target_length_km {target_length_km}, slider {self.len_km_to_slider(target_length_km)}")

        self.path_length_slider.blockSignals(True)
        self.path_length_slider.setValue(self.len_km_to_slider(target_length_km))
        self.path_length_slider.blockSignals(False)

        self.resize_to_target_path_length(target_length_km)

    def update_rotation_from_slider(self):
        value = self.rotation_slider.value()
        self.rotation_input.blockSignals(True)
        self.rotation_input.setText(str(value))
        self.rotation_input.blockSignals(False)
        self.rotation = value
        self.update_final_gpx()

    def update_rotation_from_input(self):
        try:
            value = int(self.rotation_input.text())
        except:
            return
        self.rotation_slider.blockSignals(True)
        self.rotation_slider.setValue(value)
        self.rotation_slider.blockSignals(False)
        self.rotation = value
        self.update_final_gpx()

    def update_hor_scale_from_slider(self):
        value = self.hor_scale_slider.value()
        self.hor_scale_input.blockSignals(True)
        self.hor_scale_input.setText(f"{value}")
        self.hor_scale_input.blockSignals(False)
        self.hor_scale = value / 100.0
        self.update_final_gpx()

    def update_hor_scale_from_input(self):
        try:
            value = int(self.hor_scale_input.text())
        except:
            return
        self.hor_scale_slider.blockSignals(True)
        self.hor_scale_slider.setValue(value)
        self.hor_scale_slider.blockSignals(False)
        self.hor_scale = value / 100.0
        self.update_final_gpx()

    def move_path_to_center(self):
        self.map_view.page().runJavaScript("map.getCenter()", self.move_path_to_center_js_cb)

    def move_path_to_center_js_cb(self, map_center):
        if not map_center:
            return

        center_lat, center_lon = self.svg_gpx_manager.get_path_center_lat_lon(self.gpx_data_2_scaled_translated)

        lat_offset = map_center["lat"] - center_lat
        lon_offset = map_center["lng"] - center_lon

        self.gpx_data_2_scaled_translated = self.translate_gpx_path(self.gpx_data_2_scaled_translated, lat_offset, lon_offset)

        self.update_final_gpx()

    def poll_marker_drag_end(self):
        self.map_view.page().runJavaScript("window.markerDragEnded", self.handle_marker_drag_end)

    def handle_marker_drag_end(self, dragEnded):
        if dragEnded:
            self.map_view.page().runJavaScript("JSON.stringify(window.gpxPolyline.getLatLngs())", self.translate_gpx_with_marker)
            self.map_view.page().runJavaScript("window.markerDragEnded = false;")

    def translate_gpx_with_marker(self, js_result):
        try:
            coords_list = json.loads(js_result)
        except Exception as e:
            coords_list = None
            print("Error parsing JS result in _update_gpx_from_marker:", e)

        gpx_from_map = copy.deepcopy(self.gpx_data_2_scaled_translated)
        if coords_list is not None:
            i = 0
            for track in gpx_from_map.tracks:
                for segment in track.segments:
                    for p in segment.points:
                        if i < len(coords_list):
                            p.latitude = coords_list[i]["lat"]
                            p.longitude = coords_list[i]["lng"]
                            i += 1

            center_lat_prev, center_lon_prev = self.svg_gpx_manager.get_path_center_lat_lon(self.gpx_data_2_scaled_translated)
            center_lat_new, center_lon_new = self.svg_gpx_manager.get_path_center_lat_lon(gpx_from_map)

            lat_offset = center_lat_new - center_lat_prev
            lon_offset = center_lon_new - center_lon_prev

            self.gpx_data_2_scaled_translated = self.translate_gpx_path(self.gpx_data_2_scaled_translated, lat_offset, lon_offset)

            self.update_final_gpx()

    def fix_lat_lon_scaling(self, gpx):
        """Adjust longitudes so that degrees produce equal distances as latitudes.
        This uses the average latitude to compute the correction factor.
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
        avg_lat = lat_sum / count
        # At avg_lat, 1 degree of longitude is ~cos(avg_lat) times 1 degree of latitude.
        factor = 1 / math.cos(math.radians(avg_lat))
        # Adjust longitudes relative to their average.
        center_lon = lon_sum / count
        for track in new_gpx.tracks:
            for segment in track.segments:
                for p in segment.points:
                    p.longitude = center_lon + (p.longitude - center_lon) * factor
        return new_gpx


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1000, 800)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
