"""Owner settings helper: read-only defaults and explicit, verifiable REST changes."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import unquote

from tools import configure_repository as settings


class FakeGitHub:
    def __init__(self, config, *, desired=False):
        self.config = config
        self.calls = []
        self.denied = set()
        self.ignore_settings_write = False
        self.repository = {
            "full_name": config["repository"], "default_branch": "main", **config["settings"],
        }
        self.topics = list(config["topics"]) if desired else []
        self.labels = copy.deepcopy(config["labels"]) if desired else []
        self.protection = self.protected(config["branch_protection"]) if desired else None
        self.reporting = desired
        if not desired:
            self.repository["description"] = ""

    @staticmethod
    def protected(payload):
        return {
            "required_status_checks": copy.deepcopy(payload["required_status_checks"]),
            "required_pull_request_reviews": copy.deepcopy(payload["required_pull_request_reviews"]),
            "restrictions": None,
            **{key: {"enabled": payload[key]} for key in settings.FLAGS},
        }

    def request(self, method, path, payload=None, *, paginate=False):
        self.calls.append((method, path, copy.deepcopy(payload), paginate))
        base = "repos/" + self.config["repository"]
        suffix = path.removeprefix(base)
        if method != "GET" and suffix in self.denied:
            raise settings.ApiError("Resource not accessible by integration (HTTP 403)", 403)
        if suffix == "":
            if method == "PATCH" and not self.ignore_settings_write:
                self.repository.update(payload)
            return copy.deepcopy(self.repository)
        if suffix == "/topics":
            if method == "PUT":
                self.topics = payload["names"]
            return {"names": list(self.topics)}
        if suffix == "/labels?per_page=100":
            assert method == "GET" and paginate
            return [copy.deepcopy(self.labels[:1]), copy.deepcopy(self.labels[1:])]
        if suffix == "/labels":
            assert method == "POST"
            self.labels.append(copy.deepcopy(payload))
            return copy.deepcopy(payload)
        if suffix.startswith("/labels/"):
            assert method == "PATCH"
            name = unquote(suffix.removeprefix("/labels/"))
            label = next(label for label in self.labels if label["name"] == name)
            label.update(name=payload["new_name"], color=payload["color"], description=payload["description"])
            return copy.deepcopy(label)
        if suffix == "/branches/main/protection":
            if method == "PUT":
                assert "branch" not in payload
                self.protection = self.protected(payload)
            if self.protection is None:
                raise settings.ApiError("Branch not protected (HTTP 404)", 404)
            return copy.deepcopy(self.protection)
        if suffix == "/private-vulnerability-reporting":
            if method == "PUT":
                assert payload is None
                self.reporting = True
                return None
            return {"enabled": self.reporting}
        raise AssertionError((method, path, payload))


class RepositorySettingsTests(unittest.TestCase):
    def setUp(self):
        self.config = settings.load_config(settings.DEFAULT_CONFIG)

    def run_config(self, api, *, apply=False):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = settings.configure(self.config, api, apply=apply)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_default_command_only_reads_and_reports_pending_sections(self):
        api = FakeGitHub(self.config)
        stdout = io.StringIO()
        with patch.object(settings, "GitHub", return_value=api), redirect_stdout(stdout):
            self.assertEqual(settings.main([]), 1)
        self.assertTrue(api.calls)
        self.assertTrue(all(call[0] == "GET" for call in api.calls))
        self.assertEqual(stdout.getvalue().count("Pendente:"), 5)

    def test_matching_settings_are_clean_and_unconfigured_labels_are_preserved(self):
        api = FakeGitHub(self.config, desired=True)
        api.labels.append({"name": "custom", "color": "abcdef", "description": "Kept"})
        result, stdout, stderr = self.run_config(api)
        self.assertEqual((result, stderr), (0, ""))
        self.assertEqual(stdout.count("OK:"), 5)
        self.assertTrue(all(call[0] == "GET" for call in api.calls))
        self.assertTrue(any(label["name"] == "custom" for label in api.labels))

    def test_apply_uses_documented_payloads_then_confirms_each_section(self):
        api = FakeGitHub(self.config)
        first = copy.deepcopy(self.config["labels"][0])
        first["description"] = "Old"
        api.labels = [first, {"name": "custom", "color": "abcdef", "description": "Kept"}]
        result, stdout, stderr = self.run_config(api, apply=True)
        self.assertEqual((result, stderr), (0, ""))
        self.assertEqual(stdout.count("Aplicado e conferido:"), 5)
        writes = [call for call in api.calls if call[0] != "GET"]
        self.assertFalse(any(call[0] == "DELETE" for call in writes))
        label_patch = next(call for call in writes if call[0] == "PATCH" and "/labels/" in call[1])
        self.assertEqual(set(label_patch[2]), {"new_name", "color", "description"})
        protection = next(call for call in writes if call[1].endswith("/protection"))
        self.assertEqual(protection[0], "PUT")
        self.assertEqual(protection[2]["required_status_checks"]["contexts"], ["tests", "repository"])
        self.assertEqual(protection[2]["required_pull_request_reviews"]["required_approving_review_count"], 0)
        self.assertNotIn("branch", protection[2])
        self.assertTrue(any(label["name"] == "custom" for label in api.labels))

    def test_403_is_reported_and_does_not_claim_partial_changes_are_complete(self):
        api = FakeGitHub(self.config)
        api.denied = {"", "/topics", "/branches/main/protection", "/private-vulnerability-reporting"}
        result, stdout, stderr = self.run_config(api, apply=True)
        self.assertEqual(result, 1)
        self.assertEqual(stderr.count("Não concluído:"), 4)
        self.assertIn("proprietário/administrador", stderr)
        self.assertIn("Aplicado e conferido: Labels", stdout)
        self.assertNotIn("Aplicado e conferido: Tópicos", stdout)
        self.assertTrue(settings.matches("labels", api.labels, self.config["labels"]))

    def test_success_response_without_actual_change_is_not_reported_as_applied(self):
        api = FakeGitHub(self.config, desired=True)
        api.repository["description"] = "Old"
        api.ignore_settings_write = True
        result, stdout, stderr = self.run_config(api, apply=True)
        self.assertEqual(result, 1)
        self.assertIn("conferência posterior", stderr)
        self.assertNotIn("Aplicado e conferido:", stdout)

    def test_wrong_repository_or_default_branch_prevents_any_mutation(self):
        for key, value in (("full_name", "another/project"), ("default_branch", "develop")):
            with self.subTest(key=key):
                api = FakeGitHub(self.config)
                api.repository[key] = value
                with self.assertRaises(settings.ConfigError):
                    self.run_config(api, apply=True)
                self.assertTrue(all(call[0] == "GET" for call in api.calls))

    def test_invalid_configuration_is_rejected_before_any_api_call(self):
        variants = []
        for field, value in (("repository", "owner/repo;echo bad"), ("topics", ["duplicate", "duplicate"]),
                             ("private_vulnerability_reporting", False)):
            config = copy.deepcopy(self.config)
            config[field] = value
            variants.append(config)
        config = copy.deepcopy(self.config)
        config["settings"]["visibility"] = "private"
        variants.append(config)
        config = copy.deepcopy(self.config)
        config["labels"][0]["color"] = "not-hex"
        variants.append(config)
        config = copy.deepcopy(self.config)
        config["branch_protection"]["required_status_checks"]["contexts"] = []
        variants.append(config)
        config = copy.deepcopy(self.config)
        config["settings"]["has_wiki"] = "false"
        variants.append(config)
        config = copy.deepcopy(self.config)
        config["settings"]["homepage"] = "https://:password@example.invalid"
        variants.append(config)
        for config in variants:
            with self.subTest(config=config):
                api = FakeGitHub(config)
                with self.assertRaises(settings.ConfigError):
                    settings.configure(config, api, apply=True)
                self.assertEqual(api.calls, [])

    def test_malformed_file_fails_before_constructing_or_calling_api(self):
        with TemporaryDirectory() as temporary:
            config = Path(temporary) / "settings.json"
            config.write_text("{malformed", encoding="utf-8")
            with patch.object(settings, "GitHub") as api, redirect_stderr(io.StringIO()):
                self.assertEqual(settings.main(["--config", str(config), "--apply"]), 2)
            api.assert_not_called()

    def test_gh_payload_uses_stdin_and_arguments_without_shell_or_tokens(self):
        payload = {"names": ["literal $(not-executed)"]}
        response = subprocess.CompletedProcess([], 0, '{"names": []}', "")
        with patch.object(settings.subprocess, "run", return_value=response) as run:
            self.assertEqual(settings.GitHub().request("PUT", "repos/owner/name/topics", payload), {"names": []})
        arguments, options = run.call_args.args[0], run.call_args.kwargs
        self.assertEqual(arguments[:3], ["gh", "api", "--hostname"])
        self.assertIn("github.com", arguments)
        self.assertEqual(arguments[-2:], ["--input", "-"])
        self.assertEqual(json.loads(options["input"]), payload)
        self.assertIs(options["shell"], False)
        self.assertNotIn("$(not-executed)", " ".join(arguments))
        self.assertNotIn("env", options)

    def test_gh_403_preserves_actionable_status_without_retrying_credentials(self):
        response = subprocess.CompletedProcess([], 1, "", "gh: Resource not accessible by integration (HTTP 403)")
        with patch.object(settings.subprocess, "run", return_value=response) as run:
            with self.assertRaises(settings.ApiError) as raised:
                settings.GitHub().request("PATCH", "repos/owner/name", {"has_wiki": False})
        self.assertEqual(raised.exception.status, 403)
        self.assertEqual(run.call_count, 1)

    def test_gh_pagination_decodes_concatenated_json_arrays_without_slurp(self):
        first = [{"name": "bug", "color": "d73a4a", "description": "Falha"}]
        second = [{"name": "area: estoque", "color": "0e8a16", "description": "Estoque"}]
        response = subprocess.CompletedProcess(
            [], 0, " \n" + json.dumps(first) + "\n\t " + json.dumps(second) + " \n", ""
        )
        with patch.object(settings.subprocess, "run", return_value=response) as run:
            actual = settings.GitHub().request(
                "GET", "repos/owner/name/labels?per_page=100", paginate=True
            )
        self.assertEqual(actual, [first, second])
        arguments = run.call_args.args[0]
        self.assertIn("--paginate", arguments)
        self.assertNotIn("--slurp", arguments)


if __name__ == "__main__":
    unittest.main()
