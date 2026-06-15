"""Secrets tests — stdlib unittest only (sops mocked). Run: python -m unittest discover tests -v"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from console.core import secrets
from console.core.secrets import (
    PlaintextRefused,
    SecretsManifest,
    SecretsUnconfigured,
)

MANIFEST_YML = """\
actions: []
secrets:
  file: secrets/test.sops.yaml
  encrypted_suffixes: [_token, _key, _webhook, _password, _secret]
  derived:
    ghcr_pull_token: image:ghcr-pull-secret
    deadman_webhook: alerts:set-discord
"""


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self._old_target = os.environ.get("CONSOLE_TARGET_DIR")

    def tearDown(self):
        if self._old_target is None:
            os.environ.pop("CONSOLE_TARGET_DIR", None)
        else:
            os.environ["CONSOLE_TARGET_DIR"] = self._old_target

    def _target(self, actions_yml: str | None) -> Path:
        root = Path(tempfile.mkdtemp())
        if actions_yml is not None:
            (root / "console.actions.yml").write_text(actions_yml, encoding="utf-8")
        os.environ["CONSOLE_TARGET_DIR"] = str(root)
        return root

    def test_manifest_parsed(self):
        root = self._target(MANIFEST_YML)
        m = secrets.load_manifest()
        self.assertEqual(m.file, root / "secrets/test.sops.yaml")
        self.assertIn("_token", m.encrypted_suffixes)
        self.assertEqual(m.derived["ghcr_pull_token"], "image:ghcr-pull-secret")
        self.assertEqual(m.derived["deadman_webhook"], "alerts:set-discord")

    def test_missing_section_fails_clearly(self):
        self._target("actions: []\n")
        with self.assertRaises(SecretsUnconfigured) as ctx:
            secrets.load_manifest()
        self.assertIn("secrets:", str(ctx.exception))  # tells the operator what to declare

    def test_missing_file_fails_clearly(self):
        self._target(None)
        with self.assertRaises(SecretsUnconfigured):
            secrets.load_manifest()


class GuardTests(unittest.TestCase):
    def _manifest(self, tmp: Path) -> SecretsManifest:
        return SecretsManifest(
            file=tmp / "s.sops.yaml",
            encrypted_suffixes=("_token", "_webhook"),
            derived={},
        )

    def test_suffix_guard_blocks_plaintext_bound_names(self):
        m = self._manifest(Path(tempfile.mkdtemp()))
        with self.assertRaises(PlaintextRefused):
            secrets.set_value(m, "my_setting", "v")

    def test_leak_guard_detects_unencrypted_write(self):
        tmp = Path(tempfile.mkdtemp())
        m = self._manifest(tmp)
        # sops "succeeds" but the value lands readable in the raw file -> must raise
        def fake_sops(args):
            m.file.write_text("my_token: super-plain-value\nsops: {}\n", encoding="utf-8")
            return mock.Mock(stdout="", returncode=0)

        with mock.patch.object(secrets, "_sops", side_effect=fake_sops):
            with self.assertRaises(secrets.ConsoleError) as ctx:
                secrets.set_value(m, "my_token", "super-plain-value")
        self.assertIn("LEAK GUARD", str(ctx.exception))

    def test_encrypted_write_passes(self):
        tmp = Path(tempfile.mkdtemp())
        m = self._manifest(tmp)

        def fake_sops(args):
            m.file.write_text("my_token: ENC[AES256_GCM,data:xxxx]\nsops: {}\n", encoding="utf-8")
            return mock.Mock(stdout="", returncode=0)

        with mock.patch.object(secrets, "_sops", side_effect=fake_sops):
            secrets.set_value(m, "my_token", "super-plain-value")  # no raise

    def test_force_allows_nonconforming_name(self):
        tmp = Path(tempfile.mkdtemp())
        m = self._manifest(tmp)

        def fake_sops(args):
            m.file.write_text("plain_name: ENC[AES256_GCM,data:xxxx]\nsops: {}\n", encoding="utf-8")
            return mock.Mock(stdout="", returncode=0)

        with mock.patch.object(secrets, "_sops", side_effect=fake_sops):
            secrets.set_value(m, "plain_name", "v", force=True)  # no raise


class ReadTests(unittest.TestCase):
    def test_list_and_get_from_decrypted(self):
        m = SecretsManifest(file=Path("x"), encrypted_suffixes=())
        with mock.patch.object(
            secrets, "_sops", return_value=mock.Mock(stdout="b_key: 2\na_token: 1\n")
        ):
            self.assertEqual(secrets.list_keys(m), ["a_token", "b_key"])
            self.assertEqual(secrets.get(m, "a_token"), "1")
            with self.assertRaises(secrets.ConsoleError):
                secrets.get(m, "missing")


if __name__ == "__main__":
    unittest.main()
