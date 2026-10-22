"""Regressões de uso verificadas na interface Qt real, sem rede."""

from dataclasses import replace
import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from liarte_core.inventory_io import write_snapshot
from tests import test_inventory as stock_tests
from tests.test_qt import APP


class InventorySearchRegressionTests(unittest.TestCase):
    setUp = stock_tests.InventoryUiTests.setUp
    tearDown = stock_tests.InventoryUiTests.tearDown
    item = stock_tests.InventoryUiTests.item
    idle = stock_tests.InventoryUiTests.idle
    load = stock_tests.InventoryUiTests.load

    def paste_search(self, text):
        field = self.item("stockSearch")
        field.forceActiveFocus()
        previous = APP.clipboard().text()
        try:
            APP.clipboard().setText(text)
            QTest.keyClick(self.window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            QTest.keyClick(self.window, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
            self.idle()
        finally:
            APP.clipboard().setText(previous)
        return field.property("text")

    def test_long_pasted_search_matches_the_filter_applied_to_results(self):
        self.load()
        query = "Produto inexistente " * 20
        displayed = self.paste_search(query)
        self.assertEqual(displayed, query[:200])
        self.assertEqual(self.c.state["selection"]["search"], displayed)
        self.assertEqual(self.c.state["count"], 0)
        self.assertTrue(self.c.state["current"])
        self.assertEqual(self.bundle.messages, [])

    def test_selected_product_keeps_full_label_until_replaced_by_search(self):
        data = stock_tests.sample()
        product = replace(data.products[0], name="Produto de nome extenso " * 15)
        write_snapshot(replace(data, products=(product, *data.products[1:])), self.base)
        self.load()
        self.c.setFilter("product", product.code)
        self.idle()
        field = self.item("stockSearch")
        label = self.c.state["productLabel"]
        self.assertGreater(len(label), 200)
        self.assertEqual(field.property("text"), label)

        query = "Outra busca extensa " * 20
        displayed = self.paste_search(query)
        self.assertEqual(displayed, query[:200])
        self.assertEqual(self.c.state["selection"]["product"], "")
        self.assertEqual(self.c.state["selection"]["search"], displayed)
        self.assertTrue(self.c.state["current"])
        self.assertEqual(self.bundle.messages, [])

    def test_search_limit_keeps_unicode_characters_whole(self):
        self.load()
        query = "a" * 199 + "🧪" + "excedente"
        displayed = self.paste_search(query)
        self.assertEqual(displayed, query[:200])
        self.assertEqual(self.c.state["selection"]["search"], displayed)
        self.assertTrue(self.c.state["current"])
        self.assertEqual(self.bundle.messages, [])
