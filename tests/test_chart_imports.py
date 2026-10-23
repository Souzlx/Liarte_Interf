"""Responsive chart regressions with controlled data and no public API calls."""

from __future__ import annotations

import unittest

from PySide6.QtCore import QObject
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest

from tests.test_interface import InterfaceTests
from tests.test_qt import APP


class ChartImportsTests(unittest.TestCase):
    setUp = InterfaceTests.setUp
    tearDown = InterfaceTests.tearDown
    item = InterfaceTests.item
    load = InterfaceTests.load

    def visible_labels(self, chart, prefix):
        pending, found = list(chart.childItems()), []
        while pending:
            child = pending.pop()
            if child.isVisible() and child.objectName().startswith(prefix):
                found.append(child)
            pending.extend(child.childItems())
        return sorted(found, key=lambda item: item.x())

    def test_month_captions_adapt_to_width_without_colliding_or_losing_endpoints(self):
        self.load()
        self.controller.setPreference("reducedMotion", True)
        chart = self.item("monthlyChart")
        chart.setProperty("points", [
            {"period": f"{2023 + i // 12}-{1 + i % 12:02d}", "label": str(i), "value": i + 1}
            for i in range(48)
        ])
        metrics = chart.findChild(QObject, "monthlyCategoryMetrics")
        normal_font = metrics.property("font")
        wide_font = QFont(normal_font)
        wide_font.setPixelSize(24)
        # Windows measured wider month captions than Linux. Exercise that
        # geometry here as well, preserving caption centers and full labels.
        for font in (normal_font, wide_font):
            metrics.setProperty("font", font)
            counts = []
            for width in (500, 1380):
                self.window.resize(width, 900)
                QTest.qWait(50)
                labels = self.visible_labels(chart, "monthTick")
                self.assertGreaterEqual(len(labels), 2)
                self.assertEqual(labels[0].property("text"), "jan/23")
                self.assertEqual(labels[-1].property("text"), "dez/26")
                self.assertAlmostEqual(labels[0].x() + labels[0].width() / 2,
                                       chart.property("plotLeft"), delta=0.1)
                self.assertAlmostEqual(labels[-1].x() + labels[-1].width() / 2,
                                       chart.property("plotLeft") + chart.property("plotWidth"), delta=0.1)
                for index, label in enumerate(labels):
                    self.assertGreaterEqual(label.x(), 0)
                    self.assertLessEqual(label.x() + label.width(), chart.width() + 0.1)
                    if index:
                        previous = labels[index - 1]
                        self.assertGreaterEqual(label.x() - previous.x() - previous.width(), 3)
                counts.append(len(labels))
            self.assertGreater(counts[1], counts[0])
        self.assertEqual(self.bundle.messages, [])

    def test_axis_margin_and_labels_fit_negative_large_and_tiny_values(self):
        self.load()
        self.controller.setPreference("reducedMotion", True)
        self.window.resize(500, 900)
        chart = self.item("monthlyChart")
        chart.setProperty("allowNegative", True)
        for values in ((-120000, 200000), (0, 0.000001), (0, 1000000000), (0, 0.001)):
            chart.setProperty("points", [
                {"period": f"2026-{i + 1:02d}", "label": str(i), "value": value}
                for i, value in enumerate(values)
            ])
            QTest.qWait(30)
            labels = self.visible_labels(chart, "monthlyAxisTick")
            self.assertGreaterEqual(len(labels), 2)
            self.assertEqual(len({label.property("text") for label in labels}), len(labels))
            for label in labels:
                self.assertGreaterEqual(label.y(), 0)
                self.assertLessEqual(label.y() + label.height(), chart.height())
                self.assertLessEqual(label.x() + label.width(), chart.property("plotLeft"))
                self.assertGreaterEqual(label.width(), label.property("contentWidth"))
        self.assertEqual(self.bundle.messages, [])

    def test_origins_show_readable_small_amounts_and_keep_full_country_names_accessible(self):
        self.load()
        snapshot = self.provider.snapshot
        self.window.resize(500, 900)
        chart = self.item("originChart")
        country = "Origem com uma descrição muito longa para a janela compacta"
        chart.setProperty("rows", [{"label": country, "value": 0.0000014, "share": "100,0%"}])
        APP.processEvents()
        QTest.qWait(30)
        self.assertEqual(self.item("originAmount0").property("text"), "US$ 1,40")
        label, share = self.item("originLabel0"), self.item("originShare0")
        self.assertEqual(label.property("text"), country)
        self.assertLessEqual(label.x() + label.width(), share.x())
        self.assertIs(self.provider.snapshot, snapshot)
        self.assertEqual(self.bundle.messages, [])
