"""
Tests for HCAD row mutations: append, cell updates, delete row, and compression state toggling.
"""
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


class TestMutations(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_append_uncompressed(self):
        file_path = self.dir_path / "mut_uncompressed.hcad"
        columns = [Column(0, 'i'), Column(1, 'f')]
        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_NONE)

        # Append single row
        hf.append_row([10, 1.5])
        self.assertEqual(hf.row_count, 1)

        # Append multiple rows
        hf.append_rows([[20, 2.5], [30, 3.5]])
        self.assertEqual(hf.row_count, 3)

        table = hf.read()
        self.assertEqual(len(table), 3)
        self.assertEqual(table.get_row(2)[0], 30)

    def test_append_compressed(self):
        file_path = self.dir_path / "mut_compressed.hcad"
        columns = [Column(0, 'i'), Column(1, 'f')]
        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_ZLIB)

        hf.append_rows([[1, 1.0], [2, 2.0]])
        self.assertEqual(hf.row_count, 2)

        hf.append_row([3, 3.0])
        self.assertEqual(hf.row_count, 3)

        table = hf.read()
        self.assertEqual(len(table), 3)
        self.assertEqual(table.get_row(2), [3, 3.0])

    def test_update_cell_uncompressed(self):
        file_path = self.dir_path / "update_uncompressed.hcad"
        columns = [Column(0, 'i'), Column(1, 'i')]
        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_NONE)
        hf.append_rows([[10, 20], [30, 40], [50, 60]])

        # Update row 1, column 1 (value 40 -> 999)
        hf.update_cell(row_idx=1, col_id_or_idx=1, value=999)

        table = hf.read()
        self.assertEqual(table.get_row(1), [30, 999])
        self.assertEqual(table.get_row(0), [10, 20])
        self.assertEqual(table.get_row(2), [50, 60])

    def test_update_cell_compressed(self):
        file_path = self.dir_path / "update_compressed.hcad"
        columns = [Column(0, 'i'), Column(1, 'i')]
        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_ZLIB)
        hf.append_rows([[10, 20], [30, 40]])

        hf.update_cell(row_idx=0, col_id_or_idx=0, value=777)
        table = hf.read()
        self.assertEqual(table.get_row(0), [777, 20])

    def test_delete_row(self):
        file_path = self.dir_path / "del_uncompressed.hcad"
        columns = [Column(0, 'i')]
        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_NONE)
        hf.append_rows([[1], [2], [3], [4]])

        # Delete intermediate row (row 1, value 2)
        hf.delete_row(1)
        self.assertEqual(hf.row_count, 3)
        table = hf.read()
        self.assertEqual([r[0] for r in table], [1, 3, 4])

        # Delete last row (value 4)
        hf.delete_row(2)
        self.assertEqual(hf.row_count, 2)
        table = hf.read()
        self.assertEqual([r[0] for r in table], [1, 3])

    def test_compression_toggling(self):
        file_path = self.dir_path / "toggle.hcad"
        columns = [Column(0, 'i'), Column(1, 'H h H')]
        hf = HCADFile.create(file_path, columns, compression=COMPRESSION_NONE)
        hf.append_rows([[1, (10, -20, 30)], [2, (100, -200, 300)]])

        # Compress in-place
        self.assertFalse(hf.is_compressed)
        hf.compress()
        self.assertTrue(hf.is_compressed)

        table = hf.read()
        self.assertEqual(len(table), 2)
        self.assertEqual(table.get_row(1), [2, (100, -200, 300)])

        # Decompress in-place
        hf.decompress()
        self.assertFalse(hf.is_compressed)

        table2 = hf.read()
        self.assertEqual(len(table2), 2)
        self.assertEqual(table2.get_row(1), [2, (100, -200, 300)])


if __name__ == '__main__':
    unittest.main()
