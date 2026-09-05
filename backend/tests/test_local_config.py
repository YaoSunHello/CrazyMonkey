from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.local_config import (
    GEMINI_BASE_URL, MAX_ENV_BYTES, LocalConfigError, config_status, load_local_config,
)


class LocalConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / ".env"

    def write(self, content):
        self.path.write_text(content)

    def test_legacy_gemini_key_maps_to_google_without_openai_routing(self):
        self.write("API_KEY_AI=sentinel-gemini-secret\nLLM_MODEL=gemini-test-model\nAPI_KEY_OPENAI=sentinel-openai-secret\nAPI_URL_OPENAI=https://api.openai.com/v1\n")
        environment = {}
        before = self.path.read_bytes()
        status = load_local_config(self.path, environ=environment)
        self.assertEqual(environment["LLM_API_KEY"], "sentinel-gemini-secret")
        self.assertEqual(environment["LLM_BASE_URL"], GEMINI_BASE_URL)
        self.assertEqual(environment["LLM_MODEL"], "gemini-test-model")
        self.assertTrue(status["ready"])
        self.assertEqual(status["provider"], "gemini")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertNotIn("sentinel-gemini-secret", json.dumps(status))
        self.assertNotIn("sentinel-openai-secret", json.dumps(status))
        self.assertNotIn("api.openai.com", json.dumps(status))

    def test_explicit_process_values_override_file_and_are_not_normalized(self):
        self.write("LLM_API_KEY=file-key\nLLM_BASE_URL=https://file.example\nLLM_MODEL=gemini-file\nAPI_KEY_AI=file-alias\n")
        environment = {"LLM_API_KEY": "process-key", "LLM_BASE_URL": "https://process.example", "LLM_MODEL": "gemini-process", "API_KEY_AI": "process-alias"}
        expected = dict(environment)
        status = load_local_config(self.path, environ=environment)
        self.assertEqual(environment, expected)
        self.assertFalse(status["ready"])
        self.assertFalse(status["gemini_endpoint"])

    def test_explicit_empty_process_values_are_not_filled_from_aliases(self):
        self.write("LLM_MODEL=gemini-test\nAPI_KEY_AI=sentinel-secret\nLLM_API_KEY=file-key\n")
        environment = {"LLM_API_KEY": "", "LLM_BASE_URL": ""}
        status = load_local_config(self.path, environ=environment)
        self.assertEqual(environment["LLM_API_KEY"], "")
        self.assertEqual(environment["LLM_BASE_URL"], "")
        self.assertFalse(status["ready"])

    def test_explicit_file_llm_key_takes_precedence_over_legacy_alias(self):
        self.write("LLM_MODEL=gemini-test\nLLM_API_KEY=canonical-key\nAPI_KEY_AI=legacy-key\n")
        environment = {}
        load_local_config(self.path, environ=environment)
        self.assertEqual(environment["LLM_API_KEY"], "canonical-key")

    def test_non_gemini_models_do_not_map_keys_or_google_endpoint(self):
        for model in ("gpt-test", "unknown", " gemini-test", "gemini-test\nprivate"):
            with self.subTest(model=model):
                self.write("API_KEY_AI=sentinel-secret\nAPI_KEY_OPENAI=other-sentinel\nAPI_URL_OPENAI=https://api.openai.com/v1\n")
                environment = {"LLM_MODEL": model}
                status = load_local_config(self.path, environ=environment)
                self.assertNotIn("LLM_API_KEY", environment)
                self.assertNotIn("LLM_BASE_URL", environment)
                self.assertIsNone(status["provider"])
                self.assertIsNone(status["model"])
                self.assertFalse(status["ready"])

    def test_quoting_comments_and_literal_interpolation_do_not_execute(self):
        self.write('export LLM_MODEL="gemini-test" # comment\nAPI_KEY_AI=\'literal-${SENSITIVE_VALUE}-$(touch should-not-exist)\'\nUNRELATED=ignored\n')
        environment = {"SENSITIVE_VALUE": "sentinel-private"}
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            status = load_local_config(self.path, environ=environment)
        self.assertEqual(environment["LLM_API_KEY"], "literal-${SENSITIVE_VALUE}-$(touch should-not-exist)")
        self.assertNotIn("UNRELATED", environment)
        self.assertNotIn("sentinel-private", output.getvalue() + json.dumps(status))
        self.assertFalse((self.root / "should-not-exist").exists())
        self.assertFalse(status["ready"])  # Embedded whitespace is not a valid API credential.

    def test_missing_file_does_not_search_parent_directories(self):
        self.write("LLM_MODEL=gemini-unrelated\nAPI_KEY_AI=unrelated-secret\n")
        environment = {}
        status = load_local_config(self.root / "child" / ".env", environ=environment)
        self.assertEqual(environment, {})
        self.assertFalse(status["local_env_loaded"])
        self.assertFalse(status["ready"])

    def test_existing_process_config_can_be_used_without_file(self):
        environment = {"LLM_API_KEY": "process-secret", "LLM_MODEL": "gemini-process", "LLM_BASE_URL": GEMINI_BASE_URL.rstrip("/")}
        status = load_local_config(self.path, environ=environment)
        self.assertTrue(status["ready"])
        self.assertFalse(status["local_env_loaded"])

    def test_status_suppresses_key_masquerading_as_model_and_emits_no_output(self):
        environment = {"LLM_API_KEY": "gemini-secret-token", "LLM_MODEL": "gemini-secret-token", "LLM_BASE_URL": GEMINI_BASE_URL}
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            status = config_status(environment)
        self.assertIsNone(status["model"])
        self.assertFalse(status["ready"])
        self.assertNotIn("gemini-secret-token", json.dumps(status) + output.getvalue())
        self.assertTrue(all(isinstance(value, bool) for value in status["present"].values()))

    def test_malformed_and_oversized_files_fail_without_exposing_contents(self):
        for content in ('API_KEY_AI="sentinel-secret\n', "#" * (MAX_ENV_BYTES + 1)):
            self.write(content)
            output = io.StringIO()
            environment = {}
            with redirect_stdout(output), redirect_stderr(output):
                with self.assertRaises(LocalConfigError) as caught:
                    load_local_config(self.path, environ=environment)
            self.assertNotIn("sentinel-secret", str(caught.exception) + output.getvalue())
            self.assertEqual(environment, {})

    def test_symlink_file_is_rejected(self):
        target = self.root / "source.env"
        target.write_text("API_KEY_AI=sentinel-secret\n")
        self.path.symlink_to(target)
        with self.assertRaisesRegex(LocalConfigError, "regular file"):
            load_local_config(self.path, environ={})

    def test_default_mutates_only_the_selected_process_environment(self):
        self.write("LLM_MODEL=gemini-test\nAPI_KEY_AI=sentinel-secret\n")
        with patch.dict(os.environ, {}, clear=True):
            status = load_local_config(self.path)
            self.assertEqual(os.environ["LLM_API_KEY"], "sentinel-secret")
            self.assertTrue(status["ready"])


if __name__ == "__main__":
    unittest.main()
