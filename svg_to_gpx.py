import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QPushButton, QFileDialog, QHBoxLayout, QSlider, QLabel)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import Qt, QRectF, pyqtSlot, QObject, QStandardPaths
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
        
        # Make the widget transparent and initially ignore mouse events
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
    def setSvg(self, path):
        self.svg_renderer = QSvgRenderer(path)
        self.adjustInitialScale()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.updateMask()
        self.show()
        self.update()
        
    def adjustInitialScale(self):
        if self.svg_renderer:
            svg_size = self.svg_renderer.defaultSize()
            widget_size = self.size()
            width_scale = (widget_size.width() / 3) / svg_size.width()
            height_scale = (widget_size.height() / 3) / svg_size.height()
            self.scale = min(width_scale, height_scale)
            self.position = [
                widget_size.width() / 2 - (svg_size.width() * self.scale) / 2,
                widget_size.height() / 2 - (svg_size.height() * self.scale) / 2
            ]
            self.updateMask()
    
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
            event.accept()
        else:
            event.ignore()

class MapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.map_view = QWebEngineView()
        layout.addWidget(self.map_view)
        
        self.svg_overlay = SvgOverlay(self)
        self.svg_overlay.resize(self.size())
        
        self.channel = QWebChannel()
        self.page = self.map_view.page()
        self.page.setWebChannel(self.channel)
        
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
                </script>
            </body>
            </html>
        ''')
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.svg_overlay.resize(self.size())

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Map SVG Overlay")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.map_widget = MapWidget()
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

    def load_svg(self):
        downloads_path = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open SVG File",
            downloads_path,
            "SVG Files (*.svg)"
        )
        
        if file_name:
            self.map_widget.svg_overlay.setSvg(file_name)
    
    def update_scale(self, value):
        if self.map_widget.svg_overlay.svg_renderer:
            self.map_widget.svg_overlay.scale = value / 100.0
            self.map_widget.svg_overlay.updateMask()
            self.map_widget.svg_overlay.update()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()