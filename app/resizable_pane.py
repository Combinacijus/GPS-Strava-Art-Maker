from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QSplitter
from PyQt5.QtGui import QMovie, QIcon
from PyQt5.QtCore import QSize, pyqtSignal, Qt


class PaneManager(QSplitter):
    def __init__(self, orientation, panes, min_size=100, max_size=900):
        super().__init__(orientation)
        self.min_size = min_size
        self.max_size = max_size
        self.panes = panes

        for pane in self.panes:
            self.addWidget(pane)
            pane.toggleMode.connect(self.handle_toggle_mode)

    def handle_toggle_mode(self, mode):
        sender = self.sender()  # The pane that emitted the signal.
        if mode == "normal":
            # Force all panes to normal state.
            sizes = [self.min_size] * len(self.panes)
            for pane in self.panes:
                pane.set_normal_state()
        elif mode == "maximize":
            sizes = []
            for pane in self.panes:
                if pane == sender:
                    sizes.append(self.max_size)
                    pane.set_maximized_state()
                else:
                    sizes.append(self.min_size)
                    pane.set_normal_state()
        self.setSizes(sizes)


class ResizablePane(QWidget):
    toggleMode = pyqtSignal(str)  # Emits "maximize" or "normal"

    def __init__(self, title, content_widget, pane_id):
        super().__init__()
        self.pane_id = pane_id
        self.content_widget = content_widget

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.content_widget)

        self.toggle_button = QPushButton("", self)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setMinimumHeight(30)
        self.toggle_button.setStyleSheet(
            "background-color: rgba(0, 0, 0, 0.0); border: none; padding: 6px;"
        )

        # "Expand" icon indicates that clicking will maximize.
        # "Collapse" icon indicates that clicking will restore normal state.
        self.movie_expand = QMovie("icons/icons8-expand.gif")
        self.movie_collapse = QMovie("icons/icons8-collapse.gif")
        self.movie_expand.setScaledSize(QSize(48, 48))
        self.movie_collapse.setScaledSize(QSize(48, 48))

        # Connect signals so that animations update the icon as they run.
        self.movie_expand.frameChanged.connect(self.on_expand_frame_changed)
        self.movie_collapse.frameChanged.connect(self.on_collapse_frame_changed)

        # Prime the movies so that a frame is available immediately.
        self._prime_movies()

        # Initially, we are in normal state so show the expand icon.
        self.toggle_button.setIcon(QIcon(self.movie_expand.currentPixmap()))

        self.toggle_button.clicked.connect(self.toggle_fullscreen)
        self.toggle_button.raise_()

    def _prime_movies(self):
        # Start and immediately stop the movies to ensure a valid pixmap is loaded.
        self.movie_expand.start()
        self.movie_expand.jumpToFrame(0)
        self.movie_expand.stop()
        self.movie_collapse.start()
        last_frame = self.movie_collapse.frameCount() - 1
        if last_frame < 0:
            last_frame = 0
        self.movie_collapse.jumpToFrame(last_frame)
        self.movie_collapse.stop()

    def toggle_fullscreen(self):
        if self.toggle_button.isChecked():
            # Transitioning to maximize: show collapse icon.
            self.movie_collapse.start()
            last_frame = self.movie_collapse.frameCount() - 1
            if last_frame < 0:
                last_frame = 0
            self.movie_collapse.jumpToFrame(last_frame)
            self.movie_collapse.stop()
            self.toggleMode.emit("maximize")
        else:
            # Transitioning to normal: show expand icon.
            self.movie_expand.start()
            self.movie_expand.jumpToFrame(0)
            self.movie_expand.stop()
            self.toggleMode.emit("normal")

    def on_expand_frame_changed(self, frame_number):
        self.toggle_button.setIcon(QIcon(self.movie_expand.currentPixmap()))
        if frame_number == self.movie_expand.frameCount() - 1:
            self.movie_expand.stop()

    def on_collapse_frame_changed(self, frame_number):
        self.toggle_button.setIcon(QIcon(self.movie_collapse.currentPixmap()))
        if frame_number == self.movie_collapse.frameCount() - 1:
            self.movie_collapse.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 10
        btn_width = self.toggle_button.sizeHint().width()
        btn_height = self.toggle_button.sizeHint().height()
        # Default: place at top right.
        x = max(0, self.width() - btn_width - margin - 20)
        y = 10
        # If the parent is a vertical QSplitter and this is the bottom pane,
        # then position the icon at the lower-right corner.
        parent = self.parent()
        if (parent is not None and isinstance(parent, QSplitter) and 
            parent.orientation() == Qt.Vertical and 
            parent.indexOf(self) == parent.count() - 1):
            y = max(0, self.height() - btn_height - margin)
        self.toggle_button.move(x, y)

    def set_normal_state(self):
        """Force the pane into normal state (showing the expand icon)."""
        self.toggle_button.setChecked(False)
        self.movie_expand.stop()
        self.movie_collapse.stop()
        self.movie_expand.start()
        self.movie_expand.jumpToFrame(0)
        self.movie_expand.stop()
        self.toggle_button.setIcon(QIcon(self.movie_expand.currentPixmap()))

    def set_maximized_state(self):
        """Force the pane into maximized state (showing the collapse icon)."""
        self.toggle_button.setChecked(True)
        self.movie_expand.stop()
        self.movie_collapse.stop()
        self.movie_collapse.start()
        last_frame = self.movie_collapse.frameCount() - 1
        if last_frame < 0:
            last_frame = 0
        self.movie_collapse.jumpToFrame(last_frame)
        self.movie_collapse.stop()
        self.toggle_button.setIcon(QIcon(self.movie_collapse.currentPixmap()))
