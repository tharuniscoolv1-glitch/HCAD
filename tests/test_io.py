"""
Tests for HCAD File I/O: create, read, write for both uncompressed and compressed files.
"""
import os
import tempfile
import unittest
from pathlib import Path

from src.hcad import (
    HCADFile,
    Table,
    Column,
    COMPRESSION_NONE,
    COMPRESSION_ZLIB,
)


class TestIO(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_uncompressed_roundtrip(self):
        file_path = self.dir_path / "test_uncompressed.hcad"
        columns = [
            Column(0, 'i'),
            Column(1, 'f'),
            Column(2, 'H h H'),
        ]

        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_NONE)
        table = Table(columns)
        table.add_row([1, 2.5, (10, -20, 30)])
        table.add_row([100, -9.75, (1000, -2000, 3000)])
        hf.write(table)

        read_hf = HCADFile.open(file_path)
        read_table = read_hf.read()

        self.assertEqual(len(read_table), 2)
        self.assertEqual(read_table.get_row(0)[0], 1)
        self.assertAlmostEqual(read_table.get_row(0)[1], 2.5, places=4)
        self.assertEqual(read_table.get_row(0)[2], (10, -20, 30))

        self.assertEqual(read_table.get_row(1)[0], 100)
        self.assertAlmostEqual(read_table.get_row(1)[1], -9.75, places=4)
        self.assertEqual(read_table.get_row(1)[2], (1000, -2000, 3000))

    def test_compressed_roundtrip(self):
        file_path = self.dir_path / "test_compressed.hcad"
        columns = [
            Column(0, 'i'),
            Column(1, 'c i'),
        ]

        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_ZLIB)
        table = Table(columns)
        for i in range(100):
            table.add_row([i, (b'A', i * 10)])
        hf.write(table)

        read_hf = HCADFile.open(file_path)
        self.assertTrue(read_hf.is_compressed)
        self.assertEqual(read_hf.row_count, 100)

        read_table = read_hf.read()
        self.assertEqual(len(read_table), 100)
        self.assertEqual(read_table.get_row(50), [50, (b'A', 500)])

    def test_empty_table_io(self):
        file_path = self.dir_path / "test_empty.hcad"
        columns = [Column(0, 'i')]
        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_NONE)
        read_table = hf.read()
        self.assertEqual(len(read_table), 0)


if __name__ == '__main__':
    unittest.main()
