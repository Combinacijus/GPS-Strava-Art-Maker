#!/usr/bin/env python
import json
import sys
import os
import copy
import math
import folium
from PyQt5.QtCore import Qt, QTimer
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
            self.load_svg("drawing_test.svg")
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
            "font-size: 16px; padding: 5px 15px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        self.path_length_label.setFixedWidth(250)
        slider_layout.addWidget(self.path_length_label)

        self.path_length_input = QLineEdit("1.00")
        self.path_length_input.setPlaceholderText("Length (km):")
        self.path_length_input.setStyleSheet(
            "font-size: 16px; padding: 5px 15px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
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
            "font-size: 16px; padding: 5px 15px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        self.move_path_button.clicked.connect(self.move_path_to_center)
        slider_layout.addWidget(self.move_path_button)

        main_layout.addLayout(slider_layout)

        # Combined rotation and horizontal scale row
        control_layout = QHBoxLayout()

        # Rotation control
        self.rotation_label = QLabel("Rotation (deg)")
        self.rotation_label.setStyleSheet(
            "font-size: 16px; padding: 5px 15px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        self.rotation_label.setFixedWidth(180)
        control_layout.addWidget(self.rotation_label)

        self.rotation_input = QLineEdit("0")
        self.rotation_input.setPlaceholderText("0")
        self.rotation_input.setStyleSheet(
            "font-size: 16px; padding: 5px 15px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        self.rotation_input.setFixedWidth(80)
        self.rotation_input.editingFinished.connect(self.update_rotation_from_input)
        control_layout.addWidget(self.rotation_input)

        self.rotation_slider = QSlider(Qt.Horizontal)
        self.rotation_slider.setMinimum(-180)
        self.rotation_slider.setMaximum(180)
        self.rotation_slider.setValue(0)
        self.rotation_slider.valueChanged.connect(self.update_rotation_from_slider)
        control_layout.addWidget(self.rotation_slider)

        # Horizontal scale control
        self.stretch_label = QLabel("Stretch (%)")
        self.stretch_label.setStyleSheet(
            "font-size: 16px; padding: 5px 15px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        self.stretch_label.setFixedWidth(200)
        control_layout.addWidget(self.stretch_label)

        self.stretch_input = QLineEdit("100")
        self.stretch_input.setPlaceholderText("100")
        self.stretch_input.setStyleSheet(
            "font-size: 16px; padding: 5px 15px; background-color: #007ACC; color: white; border: none; border-radius: 6px;"
        )
        self.stretch_input.setFixedWidth(80)
        self.stretch_input.editingFinished.connect(self.update_stretch_from_input)
        control_layout.addWidget(self.stretch_input)

        self.stretch_slider = QSlider(Qt.Horizontal)
        self.stretch_slider.setMinimum(25)
        self.stretch_slider.setMaximum(400)
        self.stretch_slider.setValue(100)  # default 100% = 1.0
        self.stretch_slider.valueChanged.connect(self.update_stretch_from_slider)
        control_layout.addWidget(self.stretch_slider)

        # Add the combined layout to the main layout
        main_layout.addLayout(control_layout)


        # Panes.
        self.plot_pane = ResizablePane("Plot", self.plot_canvas, "plot")
        self.map_pane = ResizablePane("Map", self.map_view, "map")
        self.splitter = PaneManager(Qt.Vertical, [self.plot_pane, self.map_pane])
        self.splitter.setSizes([300, 700])
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
                
                self.gpx_data_1_original = self.fix_lat_lon_scaling(self.gpx_data_1_original, reversed=True)  # So that after fix it won't transform
                
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
        self.stretch_slider.setValue(100)
        self.stretch_input.setPlaceholderText("100")

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
        coords = []
        if gpx_data is not None:
            for track in gpx_data.tracks:
                for segment in track.segments:
                    for point in segment.points:
                        coords.append([point.latitude, point.longitude])
        
        if not hasattr(self, 'map_initialized') or not self.map_initialized:
            # Initialize the map once with default settings and JS functions
            m = folium.Map(location=[54.9048217, 23.9592468], zoom_start=14)  # Default view
            m.get_root().html.add_child(folium.Element(
                '<script src="https://unpkg.com/leaflet-path-drag@0.0.8/Path.Drag.js"></script>'
            ))

            coords_json = json.dumps(coords)
            script = f"""
            <script>
            document.addEventListener("DOMContentLoaded", function() {{
                var map = {m.get_name()};
                window.map = map;
                
                // Initialize map elements
                window.gpxPolyline = L.polyline({coords_json}, {{
                    color: 'red',
                    weight: 2.5,
                    opacity: 1
                }}).addTo(map);
                
                window.rect = L.rectangle(gpxPolyline.getBounds(), {{
                    color: 'blue',
                    weight: 1,
                    dashArray: '5,5',
                    fillOpacity: 0.0
                }}).addTo(map);
                
                var bounds = gpxPolyline.getBounds();
                var handlePos = L.latLng(bounds.getNorth(), (bounds.getWest() + bounds.getEast()) / 2);
                window.handle = L.marker(handlePos, {{draggable: true}}).addTo(map);
                
                // Auto-zoom to path with padding if coordinates exist
                if({coords_json}.length > 0) {{
                    map.fitBounds(bounds.pad(0.3));  // Added padding
                }}
                
                // Define update function
                window.updateGPX = function(newCoords) {{
                    gpxPolyline.setLatLngs(newCoords);
                    rect.setBounds(gpxPolyline.getBounds());
                    var newBounds = gpxPolyline.getBounds();
                    
                    // Update handle position
                    var newHandlePos = L.latLng(
                        newBounds.getNorth(),
                        (newBounds.getWest() + newBounds.getEast()) / 2
                    );
                    handle.setLatLng(newHandlePos);
                    
                    // Auto-zoom to updated path with padding
                    if(newCoords.length > 0) {{
                        map.fitBounds(newBounds.pad(0.3));  // Added padding
                    }}
                }};
                
                // Rest of the script remains unchanged
                // Drag handlers (initial setup)
                var handleStartPos;
                var originalCoords;
                
                handle.on('dragstart', function(e) {{
                    handleStartPos = e.target.getLatLng();
                    originalCoords = gpxPolyline.getLatLngs().map(l => [l.lat, l.lng]);
                }});
                
                handle.on('drag', function(e) {{
                    var newPos = e.target.getLatLng();
                    var latOffset = newPos.lat - handleStartPos.lat;
                    var lngOffset = newPos.lng - handleStartPos.lng;
                    var newCoords = originalCoords.map(c => [c[0] + latOffset, c[1] + lngOffset]);
                    gpxPolyline.setLatLngs(newCoords);
                    rect.setBounds(gpxPolyline.getBounds());
                }});
                
                handle.on('dragend', function(e) {{
                    var newBounds = gpxPolyline.getBounds();
                    var newHandlePos = L.latLng(
                        newBounds.getNorth(),
                        (newBounds.getWest() + newBounds.getEast()) / 2
                    );
                    handle.setLatLng(newHandlePos);
                    window.markerDragEnded = true;
                }});
            }});
            </script>
            """
            m.get_root().html.add_child(folium.Element(script))
            map_view.setHtml(m.get_root().render())
            self.map_initialized = True
        else:
            # Update existing elements via JavaScript with auto-zoom
            coords_json = json.dumps(coords)
            js_code = f"""
            if (typeof window.updateGPX === 'function') {{
                window.updateGPX({coords_json});
                // Handle empty coordinates case
                if({len(coords)} === 0) {{
                    map.setView([54.9048217, 23.9592468], 14);
                }}
            }}
            """
            map_view.page().runJavaScript(js_code)

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

        original_length_km = self.svg_gpx_manager.calculate_gpx_length_km(self.gpx_data_2_scaled_translated)
        if original_length_km == 0:
            return

        scale_factor = target_length_km / original_length_km
        self.gpx_data_2_scaled_translated = self.scale_gpx_path(self.gpx_data_2_scaled_translated, scale_factor)
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

    def update_stretch_from_slider(self):
        value = self.stretch_slider.value()
        self.stretch_input.blockSignals(True)
        self.stretch_input.setText(f"{value}")
        self.stretch_input.blockSignals(False)
        self.hor_scale = value / 100.0
        self.update_final_gpx()

    def update_stretch_from_input(self):
        try:
            value = int(self.stretch_input.text())
        except:
            return
        self.stretch_slider.blockSignals(True)
        self.stretch_slider.setValue(value)
        self.stretch_slider.blockSignals(False)
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

    def fix_lat_lon_scaling(self, gpx, reversed=False):
        """Adjust or reverse longitude scaling so that degrees produce equal distances as latitudes.
        
        If reversed=True, it reverses the transformation by scaling longitudes back.
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
        factor = 1 / math.cos(math.radians(avg_lat))
        
        # If reversed, invert the scaling factor
        factor = 1 / factor if reversed else factor

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
