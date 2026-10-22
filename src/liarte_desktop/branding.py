"""Renderização nativa da marca, inclusive no backend de software do Qt."""

from __future__ import annotations

from pathlib import Path
from collections import OrderedDict

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQuick import QQuickImageProvider


class BrandProvider(QQuickImageProvider):
    """Aplica a cor só às letras; o arquivo original permanece intacto."""

    def __init__(self, source: Path):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.original = QImage(str(source))
        if self.original.isNull():
            raise ValueError("A logo da LIARTE não foi encontrada.")
        self.dark = QImage(self.original.size(), QImage.Format.Format_ARGB32_Premultiplied)
        self.dark.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self.dark)
        painter.drawImage(0, 0, self.original)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(self.dark.rect(), QColor("white"))
        painter.end()
        # Recorte de A já utilizado no dashboard: 22% a 47% do recurso integral.
        painter = QPainter(self.dark)
        left, right = round(self.original.width() * 0.22), round(self.original.width() * 0.47)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.setClipRect(left, 0, right - left, self.original.height())
        painter.drawImage(0, 0, self.original)
        painter.end()
        self._scaled = OrderedDict()

    def requestImage(self, identifier, size, requested_size):
        image = self.dark if identifier == "dark" else self.original
        if requested_size is not None and (
            requested_size.width() > 0 or requested_size.height() > 0
        ):
            width = requested_size.width()
            height = requested_size.height()
            if width <= 0:
                width = max(1, round(height * image.width() / image.height()))
            if height <= 0:
                height = max(1, round(width * image.height() / image.width()))
            width, height = min(width, image.width()), min(height, image.height())
            key = (identifier, width, height)
            if key not in self._scaled:
                self._scaled[key] = image.scaled(
                    width,
                    height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                while len(self._scaled) > 4:
                    self._scaled.popitem(last=False)
            self._scaled.move_to_end(key)
            image = self._scaled[key]
        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image
