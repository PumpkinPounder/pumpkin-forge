from __future__ import annotations

import unittest

from app.database import clean_release_name
from app.services import Bencode, BitPornTrackerValidator, MetadataService, TorrentService, UpdateChecker
from tools.thumbit_headless import configure_utf8_output
from main import is_stale_build_path


class CoreTests(unittest.TestCase):
    def test_bitporn_validator_is_exact(self) -> None:
        self.assertTrue(BitPornTrackerValidator.validate("https://bitporn.eu/announce/secret").valid)
        self.assertTrue(BitPornTrackerValidator.validate("https://www.bitporn.eu/announce/").valid)
        self.assertFalse(BitPornTrackerValidator.validate("http://bitporn.eu/announce/secret").valid)
        self.assertFalse(BitPornTrackerValidator.validate("https://bitporn.eu.fake.example/announce/secret").valid)
        self.assertFalse(BitPornTrackerValidator.validate("https://example.com/?url=https://bitporn.eu/announce/secret").valid)

    def test_bencode_round_trip(self) -> None:
        value = {"announce": "https://bitporn.eu/announce", "info": {"name": "Release", "private": 1}}
        decoded = Bencode.decode(Bencode.encode(value))
        self.assertEqual(decoded["announce"], b"https://bitporn.eu/announce")
        self.assertEqual(decoded["info"]["private"], 1)

    def test_piece_size_rules_are_deterministic(self) -> None:
        self.assertEqual(TorrentService._piece_length(100 * 1024 * 1024), 256 * 1024)
        self.assertEqual(TorrentService._piece_length(1024 * 1024 * 1024), 512 * 1024)
        self.assertEqual(TorrentService._piece_length(10 * 1024 * 1024 * 1024), 2 * 1024 * 1024)

    def test_stale_cross_platform_storage_path_is_detected(self) -> None:
        self.assertTrue(is_stale_build_path(r"/mnt/data/pumpkin_ui_work/Pumpkin Local Upload/J:\Pumpkin Local Upload\storage\working"))
        self.assertFalse(is_stale_build_path(r"J:\Pumpkin Local Upload\storage\working"))
        self.assertFalse(is_stale_build_path("storage/working"))

    def test_update_checker_requires_configured_github_url(self) -> None:
        result = UpdateChecker(".", {"github_version_url": ""}).check()
        self.assertEqual(result["status"], "Not configured")
        self.assertEqual(UpdateChecker._version_key("v1.10.0"), (1, 10, 0))

    def test_filename_style_release_names_are_readable(self) -> None:
        self.assertEqual(
            clean_release_name("sisswap_britt__blair_and_mae_milano_full_low_360р"),
            "sisswap britt blair and mae milano full low 360р",
        )
        query, _ = MetadataService._build_query(
            "sisswap_britt_blair_and_mae_milano_full_low_360р",
            [],
        )
        self.assertEqual(query, "sisswap britt blair and mae milano full low 360р")

    def test_thumbit_headless_exposes_utf8_output_configuration(self) -> None:
        self.assertTrue(callable(configure_utf8_output))

    def test_cached_update_status_uses_saved_github_version(self) -> None:
        checker = UpdateChecker(".", {
            "github_version_url": "https://raw.githubusercontent.com/example/repo/main/version.txt",
            "last_remote_version": "v9.9.9",
            "last_update_check_at": "2026-08-29T15:00:00+00:00",
            "last_update_error": "",
            "update_check_enabled": True,
        })
        result = checker.cached()
        self.assertEqual(result["status"], "Update available")
        self.assertEqual(result["remote_version"], "9.9.9")



if __name__ == "__main__":
    unittest.main()
