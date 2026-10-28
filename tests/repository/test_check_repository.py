"""The repository gate runs independently of the application and its dependencies."""

from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from tools import check_repository as checker


class RepositoryCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self.git("init", "--quiet")
        for name in checker.REQUIRED_FILES:
            self.write(name, "# Documentation\n" if name.endswith(".md") else "")
        self.git("add", "--all")

    def git(self, *arguments):
        return subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            capture_output=True, check=True,
        )

    def write(self, name, contents):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        return path

    def test_staged_links_images_titles_and_directory_navigation_are_accepted(self):
        self.write("docs/Guide (1).md", "# Guide\n")
        self.write("docs/Guide(2).md", "# Guide\n")
        self.write("docs/images/example.png", "synthetic image placeholder")
        self.write("README.md", """# Documentation
[Encoded](docs/Guide%20%281%29.md#section)
[Angle](<docs/Guide (1).md> "Read the guide")
[Parentheses](docs/Guide(2).md)
[Nested [label]](docs/Guide(2).md)
![Example](docs/images/example.png)
[Directory](docs/)
[Root](/docs/Guide(2).md)
[Same page](#fragment)
[External](https://example.invalid/no-network-request)
`[Code](missing-inline.md)`
```markdown
[Example only](missing-fenced.md)
```not-a-closing-fence
[Still example only](missing-fenced-again.md)
```
""")
        self.git("add", "--all")
        self.assertEqual(checker.check_repository(self.root), [])

    def test_missing_and_case_mismatched_destinations_report_source_line_and_fix(self):
        self.write("docs/Guide.md", "# Guide\n")
        self.write("README.md", "# Documentation\n[Missing](missing.md)\n[Wrong case](docs/guide.md)\n")
        self.git("add", "--all")
        errors = checker.check_repository(self.root)
        self.assertTrue(any("README.md:2:" in error and "missing.md" in error for error in errors))
        self.assertTrue(any("README.md:3:" in error and "use 'docs/Guide.md'" in error for error in errors))

    def test_existing_untracked_target_does_not_hide_a_missing_checkout_file(self):
        self.write("README.md", "[Local only](docs/untracked.md)\n")
        self.write("docs/untracked.md", "# Not staged\n")
        self.git("add", "README.md")
        self.assertTrue(any("ausente do índice Git" in error for error in checker.check_repository(self.root)))
        self.git("add", "docs/untracked.md")
        self.assertEqual(checker.check_repository(self.root), [])

    def test_relative_and_encoded_parent_traversal_are_rejected(self):
        self.write("README.md", "[Escape](../outside.txt)\n[Encoded](%2e%2e/outside.txt)\n")
        self.git("add", "README.md")
        errors = checker.check_repository(self.root)
        self.assertEqual(sum("sai da raiz" in error for error in errors), 2)

    def test_external_symlink_is_not_read_as_documentation(self):
        outside = Path(self.temporary.name) / "outside.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        link = self.root / "docs/external.md"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        self.write("README.md", "[External file](docs/external.md)\n")
        self.git("add", "--all")
        errors = checker.check_repository(self.root)
        self.assertTrue(any("link simbólico sai da raiz" in error for error in errors))
        self.assertTrue(any("arquivo Markdown aponta para fora" in error for error in errors))

    def test_generated_and_private_files_are_rejected_but_curated_assets_remain_allowed(self):
        forbidden = (
            "input/company.pbix", "input/company.pbit", "app.exe", "package.whl",
            "__pycache__/cache.pyc", ".venv/pyvenv.cfg", "build/result.txt",
            "dist/result.txt", "logs/runtime.log", "profiles/settings.ini",
            ".liarte-dev-profile/settings.ini", ".env", ".env.production",
        )
        allowed = (
            "src/liarte_core/data/estoque.liarte", "exemplos/example.xlsx",
            "docs/archive/validation/build.log", ".env.example",
        )
        for name in forbidden + allowed:
            self.write(name, "synthetic placeholder")
        self.git("add", "--all")
        errors = checker.check_repository(self.root)
        for name in forbidden:
            self.assertTrue(any(error.startswith(name + ":") for error in errors), name)
        for name in allowed:
            self.assertFalse(any(error.startswith(name + ":") for error in errors), name)

    def test_missing_required_file_fails_and_cli_returns_a_nonzero_exit(self):
        (self.root / "CONTRIBUTING.md").unlink()
        self.git("add", "--all")
        result = subprocess.run(
            [sys.executable, str(Path(checker.__file__)), "--root", str(self.root)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("CONTRIBUTING.md: arquivo essencial ausente", result.stdout)


if __name__ == "__main__":
    unittest.main()
