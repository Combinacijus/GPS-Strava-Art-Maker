import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QPushButton, QFileDialog, QHBoxLayout, QSlider, QLabel)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import Qt, QRectF, pyqtSlot, QObject, QStandardPaths, pyqtSignal
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtGui import QPainter, QRegion

class SvgOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.svg_renderer = None
        self.scale = 1.0
        self.position = [0, 0]
        self.dragging = False
        self.last_pos = None
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
    def setSvg(self, path):
        self.svg_renderer = QSvgRenderer(path)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.updateMask()
        self.show()
        self.update()
        
    def updateMask(self):
        if self.svg_renderer:
            svg_size = self.svg_renderer.defaultSize()
            scaled_width = svg_size.width() * self.scale
            scaled_height = svg_size.height() * self.scale
            mask_rect = QRectF(self.position[0], self.position[1], scaled_width, scaled_height)
            self.setMask(QRegion(mask_rect.toAlignedRect()))
        else:
            self.clearMask()
    
    def paintEvent(self, event):
        if self.svg_renderer:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            default_size = self.svg_renderer.defaultSize()
            scaled_width = default_size.width() * self.scale
            scaled_height = default_size.height() * self.scale
            target_rect = QRectF(
                self.position[0],
                self.position[1],
                scaled_width,
                scaled_height
            )
            self.svg_renderer.render(painter, target_rect)
    
    def mousePressEvent(self, event):
        if self.svg_renderer:
            svg_rect = QRectF(
                self.position[0], self.position[1],
                self.svg_renderer.defaultSize().width() * self.scale,
                self.svg_renderer.defaultSize().height() * self.scale
            )
            if svg_rect.contains(event.pos()):
                self.dragging = True
                self.last_pos = event.pos()
                event.accept()
            else:
                event.ignore()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            event.accept()
        else:
            event.ignore()
    
    def mouseMoveEvent(self, event):
        if self.dragging and self.last_pos:
            delta = event.pos() - self.last_pos
            self.position[0] += delta.x()
            self.position[1] += delta.y()
            self.last_pos = event.pos()
            self.updateMask()
            self.update()
            self.parent().updateSVGAnchorFromPosition(self.position)
            event.accept()
        else:
            event.ignore()

class Bridge(QObject):
    updateScale = pyqtSignal(float)
    
    def __init__(self, map_widget):
        super().__init__()
        self.map_widget = map_widget

    @pyqtSlot(float, float, int)
    def updateMapCenter(self, lat, lng, zoom):
        print(f"Map center: {lat}, {lng}, zoom: {zoom}")
        if hasattr(self.map_widget.main_window, 'initial_zoom') and hasattr(self.map_widget.main_window, 'initial_scale'):
            current_zoom = zoom
            scale_factor = 2 ** (current_zoom - self.map_widget.main_window.initial_zoom)
            new_scale = self.map_widget.main_window.initial_scale * scale_factor
            self.map_widget.svg_overlay.scale = new_scale
            self.updateScale.emit(new_scale)
            self.map_widget.svg_overlay.updateMask()
            self.map_widget.svg_overlay.update()

    @pyqtSlot(float, float)
    def updateSVGPosition(self, x, y):
        svg_overlay = self.map_widget.svg_overlay
        if svg_overlay.svg_renderer:
            svg_size = svg_overlay.svg_renderer.defaultSize()
            scaled_width = svg_size.width() * svg_overlay.scale
            scaled_height = svg_size.height() * svg_overlay.scale
            pos_x = x - scaled_width / 2
            pos_y = y - scaled_height / 2
            svg_overlay.position = [pos_x, pos_y]
            svg_overlay.updateMask()
            svg_overlay.update()

class MapWidget(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.map_view = QWebEngineView()
        layout.addWidget(self.map_view)
        
        self.svg_overlay = SvgOverlay(self)
        self.svg_overlay.resize(self.size())
        
        self.channel = QWebChannel()
        self.bridge = Bridge(self)
        self.channel.registerObject('qtObject', self.bridge)
        self.map_view.page().setWebChannel(self.channel)
        
        self.map_view.setHtml('''
            <!DOCTYPE html>
            <html>
            <head>
                <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css"/>
                <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
                <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
                <style>
                    #map { height: 100vh; }
                </style>
            </head>
            <body>
                <div id="map"></div>
                <script>
                    var map = L.map('map').setView([54.899, 23.9], 13);
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                        attribution: '© OpenStreetMap contributors'
                    }).addTo(map);
                    
                    var qtObject = {
                        updateMapCenter: function(lat, lng, zoom) {},
                        updateSVGPosition: function(x, y) {}
                    };
                    
                    new QWebChannel(qt.webChannelTransport, function(channel) {
                        qtObject = channel.objects.qtObject;
                    });
                    
                    var svgAnchor = null;
                    
                    function sendMapCenter() {
                        var center = map.getCenter();
                        var zoom = map.getZoom();
                        qtObject.updateMapCenter(center.lat, center.lng, zoom);
                    }
                    
                    function updateSVGPosition() {
                        if (svgAnchor) {
                            var point = map.latLngToContainerPoint(svgAnchor);
                            qtObject.updateSVGPosition(point.x, point.y);
                        }
                    }
                    
                    map.on('move', function() {
                        sendMapCenter();
                        updateSVGPosition();
                    });
                    
                    map.on('zoom', function() {
                        sendMapCenter();
                        updateSVGPosition();
                    });
                </script>
            </body>
            </html>
        ''')
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.svg_overlay.resize(self.size())
    
    def updateSVGAnchorFromPosition(self, position):
        x = position[0] + (self.svg_overlay.svg_renderer.defaultSize().width() * self.svg_overlay.scale) / 2
        y = position[1] + (self.svg_overlay.svg_renderer.defaultSize().height() * self.svg_overlay.scale) / 2
        js_code = f'''
            var point = L.point({x}, {y});
            svgAnchor = map.containerPointToLatLng(point);
        '''
        self.map_view.page().runJavaScript(js_code)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Map SVG Overlay")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.map_widget = MapWidget(self)
        main_layout.addWidget(self.map_widget)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(10, 5, 10, 5)
        
        load_button = QPushButton("Load SVG")
        load_button.clicked.connect(self.load_svg)
        controls_layout.addWidget(load_button)
        
        scale_label = QLabel("Scale:")
        controls_layout.addWidget(scale_label)
        
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setMinimum(1)
        self.scale_slider.setMaximum(200)
        self.scale_slider.setValue(100)
        self.scale_slider.valueChanged.connect(self.update_scale)
        controls_layout.addWidget(self.scale_slider)
        
        main_layout.addLayout(controls_layout)
        
        self.map_widget.bridge.updateScale.connect(self.update_slider_from_scale)

    def load_svg(self):
        downloads_path = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open SVG File",
            downloads_path,
            "SVG Files (*.svg)"
        )
        if file_name:
            self.map_widget.map_view.page().runJavaScript(
                "map.getCenter().lat + ',' + map.getCenter().lng + ',' + map.getZoom()",
                lambda result: self.on_map_data_retrieved(result, file_name)
            )

    def on_map_data_retrieved(self, result, file_name):
        parts = result.split(',')
        if len(parts) != 3:
            return
        lat, lng, zoom = parts
        self.initial_zoom = int(zoom)
        self.initial_scale = 1.0  # Initial scale set to 100%
        self.map_widget.svg_overlay.setSvg(file_name)
        self.scale_slider.setValue(int(self.initial_scale * 100))
        js_code = f"svgAnchor = L.latLng({lat}, {lng});"
        self.map_widget.map_view.page().runJavaScript(js_code)

    def update_scale(self, value):
        if hasattr(self, 'initial_zoom'):
            self.initial_scale = value / 100.0
            self.map_widget.map_view.page().runJavaScript(
                "map.getZoom()",
                lambda zoom: self.update_scale_based_on_zoom(zoom)
            )

    def update_scale_based_on_zoom(self, zoom):
        current_zoom = int(zoom)
        scale_factor = 2 ** (current_zoom - self.initial_zoom)
        new_scale = self.initial_scale * scale_factor
        self.map_widget.svg_overlay.scale = new_scale
        self.map_widget.svg_overlay.updateMask()
        self.map_widget.svg_overlay.update()
    
    def update_slider_from_scale(self, scale):
        self.scale_slider.blockSignals(True)
        self.scale_slider.setValue(int(scale * 100))
        self.scale_slider.blockSignals(False)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()