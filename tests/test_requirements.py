import stat
import unittest
from pathlib import Path

_MAX_BYTES = 64 * 1024


class Requirements(unittest.TestCase):
    def test_pyav_below_19(self):
        requirements = Path(__file__).resolve().parents[1] / "requirements.txt"
        info = requirements.stat()
        self.assertTrue(stat.S_ISREG(info.st_mode))
        self.assertLessEqual(info.st_size, _MAX_BYTES)
        with requirements.open("rb") as handle:
            raw = handle.read(_MAX_BYTES)
        lines = [
            line.partition("#")[0].strip()
            for line in raw.decode("utf-8", errors="replace").splitlines()
        ]
        self.assertIn("av<19", lines)
