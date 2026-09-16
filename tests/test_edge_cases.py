"""
Tests for HCAD edge cases, corruption recovery, zero tempfile leaks, and schema validation.
"""
import os
import struct
import tempfile
import unittest
from pathlib import Path

from src.hcad import (
    HCADFile,
    Column,
    COMPRESSION_NONE,
    COMPRESSION_ZLIB,
    CorruptedFileError,
    SchemaMismatchError,
    InvalidHeaderError,
)
from src.functions import createNewFile, validateFile


class TestEdgeCases(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_windows_empty_path(self):
        # Must not crash when path is empty string
        current_dir = Path.cwd()
        test_file = current_dir / "test_empty_path.hcad"
        try:
            createNewFile("test_empty_path.hcad", "", ["i", "f"])
            self.assertTrue(test_file.exists())
            self.assertTrue(validateFile(str(test_file)))
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_corrupted_zlib_detection(self):
        file_path = self.dir_path / "corrupt_zlib.hcad"
        columns = [Column(0, 'i')]
        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_ZLIB)
        hf.append_row([42])

        # Overwrite payload with garbage
        with open(file_path, 'r+b') as f:
            f.seek(hf.data_offset)
            f.write(b'GARBAGE_ZLIB_DATA_12345')

        # Reading must raise CorruptedFileError
        corrupt_hf = HCADFile.open(file_path)
        with self.assertRaises(CorruptedFileError):
            corrupt_hf.read()

        # validateFile must return False
        self.assertFalse(validateFile(str(file_path)))

    def test_truncated_row_detection(self):
        file_path = self.dir_path / "truncated.hcad"
        columns = [Column(0, 'i')]  # 4 bytes per row
        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_NONE)
        hf.append_row([10])

        # Append 2 stray bytes
        with open(file_path, 'ab') as f:
            f.write(b'XY')

        trunc_hf = HCADFile.open(file_path)
        with self.assertRaises(CorruptedFileError):
            trunc_hf.read()

        self.assertFalse(validateFile(str(file_path)))

    def test_no_tempfile_leaks_on_error(self):
        file_path = self.dir_path / "leak_test.hcad"
        columns = [Column(0, 'i')]
        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_NONE)

        count_before = len(list(self.dir_path.glob("tmp*")))

        # Intentionally fail during an operation
        with self.assertRaises(Exception):
            hf.append_row(["not_an_int"])

        count_after = len(list(self.dir_path.glob("tmp*")))
        self.assertEqual(count_before, count_after, "Temporary file leaked on error!")


if __name__ == '__main__':
    unittest.main()
