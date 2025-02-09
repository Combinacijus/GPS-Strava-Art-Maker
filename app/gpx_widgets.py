from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QPainter

class AspectRatioSvgWidget(QSvgWidget):
    """
    A QSvgWidget that maintains the aspect ratio of the SVG file.
    """
    def paintEvent(self, event):
        painter = QPainter(self)
        renderer = self.renderer()
        if not renderer.isValid():
            return super().paintEvent(event)
        widget_rect = self.rect()
        default_size = renderer.defaultSize()
        if default_size.isEmpty():
            target_rect = widget_rect
        else:
            default_ratio = default_size.width() / default_size.height()
            widget_ratio = widget_rect.width() / widget_rect.height()
            if widget_ratio > default_ratio:
                new_width = int(widget_rect.height() * default_ratio)
                new_height = widget_rect.height()
                x = (widget_rect.width() - new_width) // 2
                y = 0
            else:
                new_width = widget_rect.width()
                new_height = int(widget_rect.width() / default_ratio)
                x = 0
                y = (widget_rect.height() - new_height) // 2
            target_rect = QRectF(x, y, new_width, new_height)


        renderer.render(painter, target_rect)