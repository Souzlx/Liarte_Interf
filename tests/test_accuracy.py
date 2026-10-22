"""Regressions for omitted responses, cents, export scopes and PDF identities."""

from dataclasses import replace
from decimal import Decimal, localcontext
import copy
import json
from threading import Event
from unittest.mock import patch

from openpyxl import load_workbook

from liarte_core.comex import ComexError, integral
from liarte_core.domain import Period
from liarte_core.exports import export_document, pdf_source
from liarte_engine import comexstat_importacoes as engine
from liarte_engine.numeric import published_units
from liarte_engine.pdf_importacoes import consolidate_pdf_rows
from tests.test_comex import ComexFixtureCase, ExportTests, FIXTURE, Response


class AccuracyTests(ComexFixtureCase):
    # A ferramenta de conferência continua testada em modo explícito. O desktop
    # usa a resposta detalhada, sem solicitar uma segunda resposta de totais.
    verify_official_totals = True

    def test_context_cannot_round_an_imported_integer_or_fraction_of_cent(self):
        with localcontext() as context:
            context.prec = 6
            self.assertEqual(
                integral("123456789012345678901234567890.12", cents=True),
                12345678901234567890123456789012,
            )
            with self.assertRaises(ComexError):
                integral("123456789012345678901234567890.121", cents=True)
        for value in (True, None, "NaN", "Infinity", "-1", "1,000", "1e999999"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                published_units(value)

    def test_one_cent_cif_divergence_is_never_accepted_even_above_float_precision(self):
        row = copy.deepcopy(FIXTURE["general"][0])
        row.update(
            metricFOB="9007199254740992.00",
            metricFreight="0",
            metricInsurance="0",
            metricCIF="9007199254740992.01",
        )
        with self.assertRaises(engine.ComexStatError):
            engine.validate_api_row(
                row, {"29161220"}, "2026-09", "2026-09", "regression"
            )

    def test_fractional_kg_is_rejected_in_both_api_contracts(self):
        for municipal in (False, True):
            row = copy.deepcopy(FIXTURE["municipal" if municipal else "general"][0])
            row["metricKG"] = "1000.5"
            validate = (
                engine.validate_municipal_api_row
                if municipal
                else engine.validate_api_row
            )
            with (
                self.subTest(municipal=municipal),
                self.assertRaises(engine.ComexStatError),
            ):
                validate(
                    row,
                    {"2916" if municipal else "29161220"},
                    "2026-09",
                    "2026-09",
                    "regression",
                )

    def test_distinct_large_cent_amounts_have_distinct_duplicate_signatures(self):
        a, b = (copy.deepcopy(FIXTURE["general"][0]) for _ in range(2))
        a["metricFOB"], b["metricFOB"] = "9007199254740992.00", "9007199254740992.01"
        self.assertNotEqual(
            engine.api_metric_signature(a), engine.api_metric_signature(b)
        )

    def intercept_controls(self, transform):
        def receive(request, **kwargs):
            response = self.transport(request, **kwargs)
            if request.method == "POST":
                body = json.loads(request.data)
                document = json.loads(response.getvalue())
                document = transform(request.full_url, body, document)
                return Response(document)
            return response

        return patch(
            "liarte_engine.comexstat_importacoes.urllib.request.urlopen",
            side_effect=receive,
        )

    def test_omitted_detailed_row_is_detected_before_cache_or_snapshot_publication(
        self,
    ):
        def omit(url, body, document):
            if "/general?" in url and len(body["details"]) > 1:
                document["data"]["list"] = document["data"]["list"][1:]
            return document

        with (
            self.intercept_controls(omit),
            self.assertRaisesRegex(ComexError, "totais oficiais"),
        ):
            self.query()
        self.assertIsNone(self.provider.snapshot)
        self.assertFalse((self.directory / "consultas.sqlite3").exists())

    def test_one_cent_in_control_blocks_the_batch_and_keeps_previous_snapshot(self):
        self.query()
        previous = self.provider.snapshot

        def alter(url, body, document):
            if len(body["details"]) == 1 and "/cities?" in url:
                row = document["data"]["list"][0]
                row["metricFOB"] = str(Decimal(row["metricFOB"]) + Decimal(".01"))
            return document

        self.provider.force_refresh()
        with (
            self.intercept_controls(alter),
            self.assertRaisesRegex(ComexError, "totais oficiais"),
        ):
            self.query()
        self.assertIs(previous, self.provider.snapshot)

    def test_missing_or_repeated_control_does_not_become_an_empty_valid_cache(self):
        for mode in ("missing", "duplicate", "outside"):

            def alter(url, body, document):
                if len(body["details"]) == 1:
                    if mode == "missing":
                        document["data"] = {}
                    elif mode == "duplicate":
                        document["data"]["list"] *= 2
                    else:
                        document["data"]["list"][0]["monthNumber"] = "08"
                return document

            with (
                self.subTest(mode=mode),
                self.intercept_controls(alter),
                self.assertRaises(ComexError),
            ):
                self.query()
            self.assertIsNone(self.provider.snapshot)

    def test_verified_cache_needs_no_new_control_requests_for_filters(self):
        self.query()
        self.assertEqual(self.provider.snapshot.api_requests, 4)
        before = len(self.transport.calls)
        self.query(country="China")
        self.assertEqual(len(self.transport.calls), before)

    def test_zero_totals_cannot_hide_an_entirely_omitted_code_month(self):
        client = engine.ComexStatClient(min_interval=0)
        body = {
            "period": {"from": "2026-09", "to": "2026-09"},
            "filters": [{"filter": "ncm", "values": [29161220]}],
            "details": engine.DEFAULT_DETAILS,
            "metrics": engine.DEFAULT_METRICS,
        }
        control = {
            "coNcm": "29161220",
            "year": "2026",
            "monthNumber": "09",
            **dict.fromkeys(engine.DEFAULT_METRICS, "0"),
        }
        with (
            patch.object(
                client, "request_json", return_value={"data": {"list": [control]}}
            ),
            self.assertRaisesRegex(engine.ComexStatError, "totais oficiais"),
        ):
            client._verify_totals("/general", body, [], municipal=False)

    def test_pdf_does_not_merge_distinct_ncms_with_the_same_commercial_name(self):
        raw = []
        for code, cif in [("39100011", "3000.01"), ("39100012", "6000.02")]:
            row = copy.deepcopy(FIXTURE["general"][0])
            row.update(coNcm=code, metricKG="2000", metricCIF=cif)
            raw.append(row)
        data = consolidate_pdf_rows(engine.internal_product_ncms(), raw)
        self.assertEqual(len(data), 2)
        self.assertEqual({r["description"] for r in data}, {"Óleo de silicone"})
        self.assertEqual(
            sorted(r["usd_per_kg"] for r in data),
            [Decimal("1.500005"), Decimal("3.00001")],
        )

    def test_pdf_preserves_distinct_urf_keys_and_relevance_is_per_observation(self):
        raw = []
        for port, kg in [
            ("0817800 - PORTO DE SANTOS", "2000"),
            ("9999999 - PORTO DE SANTOS", "2000"),
            ("PORTO DO RJ", "600"),
            ("PORTO DO RJ", "600"),
            ("AEROPORTO DE GUARULHOS", "9000"),
        ]:
            row = copy.deepcopy(FIXTURE["general"][0])
            row.update(urf=port, metricKG=kg, metricCIF="2000")
            raw.append(row)
        data = consolidate_pdf_rows(engine.internal_product_ncms(), raw)
        self.assertEqual(len(data), 2)
        self.assertEqual(sum(r["kg"] for r in data), 4000)


class AccuracyExportTests(ComexFixtureCase):
    request = ExportTests.request
    export = ExportTests.export

    def test_direct_excel_call_rejects_duplicate_grains_and_preserves_previous_file(
        self,
    ):
        output = self.directory / "previous.xlsx"
        output.write_bytes(b"previous report")
        for municipal in (False, True):
            general = [copy.deepcopy(FIXTURE["general"][0])]
            cities = [copy.deepcopy(FIXTURE["municipal"][0])]
            (cities if municipal else general).append(
                copy.deepcopy((cities if municipal else general)[0])
            )
            with (
                self.subTest(municipal=municipal),
                self.assertRaisesRegex(ValueError, "repetido"),
            ):
                engine.create_report(
                    output,
                    engine.internal_product_ncms(),
                    general,
                    "2026-09",
                    "2026-09",
                    True,
                    cities,
                )
            self.assertEqual(output.read_bytes(), b"previous report")

    def test_export_progress_does_not_regress_or_reach_100_before_publishing(self):
        request = self.request("excel")
        events = []

        def observe(percent, stage):
            events.append(percent)
            if percent == 100:
                self.assertTrue(request.destination.is_file())

        export_document(request, Event(), observe, self.directory / "audit")
        self.assertEqual(events, sorted(events))
        self.assertEqual(events[-1], 100)

    def test_period_mismatch_and_pdf_length_mismatch_do_not_overwrite_good_files(self):
        request = self.request("excel")
        request.destination.write_bytes(b"previous valid file")
        mismatch = replace(
            request,
            selection=replace(request.selection, period=Period("2026-08", "2026-09")),
        )
        with self.assertRaisesRegex(ValueError, "período"):
            self.export(mismatch)
        self.assertEqual(request.destination.read_bytes(), b"previous valid file")
        bad = replace(
            request.snapshot, general_records=request.snapshot.general_records[:-1]
        )
        with self.assertRaisesRegex(ValueError, "incompleta"):
            pdf_source(replace(request, kind="pdf", snapshot=bad), Event())

    def test_summary_cannot_move_values_between_groups_while_preserving_total(self):
        source = [
            ["month", "city1", "SP", "2916", "desc", "China", 10, 100],
            ["month", "city2", "SP", "2916", "desc", "China", 20, 100],
        ]
        summary = [
            ["city1", "SP", "2916", 1, 1, 11, 100],
            ["city2", "SP", "2916", 1, 1, 19, 100],
        ]
        with self.assertRaisesRegex(ValueError, "divergiu"):
            engine._verify_grouped_summary(
                summary, source, (0, 1), (1, 2), (5, 6), (6, 7), 4
            )

    def test_cent_values_are_preserved_and_shown_in_excel(self):
        raw = [copy.deepcopy(FIXTURE["general"][0])]
        raw[0].update(
            metricFOB="123.45",
            metricFreight="6.78",
            metricInsurance=".90",
            metricCIF="131.13",
        )
        output = self.directory / "centavos.xlsx"
        engine.create_report(
            output, engine.internal_product_ncms(), raw, "2026-09", "2026-09", True
        )
        book = load_workbook(output)
        try:
            self.assertEqual(book["Base geral"]["G2"].value, 123.45)
            self.assertEqual(book["Base geral"]["G2"].number_format, '"US$" #,##0.00')
            self.assertEqual(book["Base geral"]["J2"].value, 131.13)
            self.assertEqual(book["Base municipal"].column_dimensions["E"].width, 64)
        finally:
            book.close()
