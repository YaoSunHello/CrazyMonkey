"""Bounded public-repository hygiene checks; failures never print secret values.

Inventory comes from Git's index, while content comes from the current working
files so an unstaged remediation is checked immediately. This is a signature
and path check, not proof that all possible credentials or private data are absent.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path, PurePosixPath


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAX_TRACKED_BYTES = 10 * 1024 * 1024
PRIVATE_WORKSTATION_PATH = re.compile(
    r"/(?:Users|home)/(?!<)[^/\s`]+/|[A-Za-z]:\\Users\\(?!<)[^\\\s`]+\\"
)
CREDENTIAL_SIGNATURES = {
    "private-key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
    "aws-access-key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "github-token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
    ),
    "openai-key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b"),
    "assigned-credential": re.compile(
        r"\b(?:api[_-]?key|secret[_-]?key|password|access[_-]?token|auth[_-]?token)"
        r"\s*[:=]\s*[\x22\x27][^\x22\x27\n]{8,}[\x22\x27]",
        re.IGNORECASE,
    ),
}


class PublicRepositoryHygieneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        git = shutil.which("git")
        if git is None:
            raise unittest.SkipTest("Git is unavailable; tracked-file hygiene cannot run.")
        try:
            result = subprocess.run(
                [git, "ls-files", "--cached", "-z"],
                cwd=REPOSITORY_ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            raise unittest.SkipTest(
                "Git's tracked-file inventory is unavailable; hygiene cannot run."
            ) from None
        cls.tracked_files = [
            path for path in result.stdout.decode("utf-8", errors="replace").split("\0")
            if path
        ]

    def test_documentation_does_not_disclose_personal_workstation_paths(self) -> None:
        findings = []
        for relative in self.tracked_files:
            path = REPOSITORY_ROOT / relative
            if path.suffix.lower() not in {".md", ".rst", ".txt"}:
                continue
            if not path.is_file() or path.is_symlink():
                continue
            for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if PRIVATE_WORKSTATION_PATH.search(line):
                    findings.append(f"{relative}:{number}: personal-workstation-path")
        self.assertFalse(findings, "Personal path disclosures (values hidden): " + "; ".join(findings))

    def test_tracked_paths_exclude_environments_caches_and_generated_artifacts(self) -> None:
        findings = []
        excluded_parts = {
            "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
            ".mypy_cache", ".ruff_cache", ".cache", ".DS_Store",
        }
        for relative in self.tracked_files:
            posix_path = PurePosixPath(relative)
            name = posix_path.name
            is_environment = name == ".env" or (
                name.startswith(".env.")
                and name not in {".env.example", ".env.sample", ".env.template"}
            )
            is_output = relative.startswith("outputs/") and name != ".gitkeep"
            if (
                is_environment
                or excluded_parts.intersection(posix_path.parts)
                or posix_path.suffix in {".pyc", ".pyo"}
                or is_output
            ):
                findings.append(f"{relative}: prohibited-generated-or-environment-path")
            path = REPOSITORY_ROOT / relative
            if path.is_file() and not path.is_symlink() and path.stat().st_size > MAX_TRACKED_BYTES:
                findings.append(f"{relative}: exceeds-10-MiB-hygiene-limit")
        self.assertFalse(findings, "Tracked-path hygiene failures: " + "; ".join(findings))

    def test_tracked_content_has_no_common_credential_signatures(self) -> None:
        findings = []
        for relative in self.tracked_files:
            path = REPOSITORY_ROOT / relative
            if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_TRACKED_BYTES:
                continue
            for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                for category, signature in CREDENTIAL_SIGNATURES.items():
                    if signature.search(line):
                        findings.append(f"{relative}:{number}: {category}")
        self.assertFalse(findings, "Credential signatures (values hidden): " + "; ".join(findings))


if __name__ == "__main__":
    unittest.main()
