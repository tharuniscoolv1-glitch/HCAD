import os
import tempfile
import unittest
from pathlib import Path

from hcad.core.column import Column
from hcad.core.constants import COMPRESSION_NONE, COMPRESSION_ZLIB
from hcad.core.exceptions import CorruptedFileError, SchemaMismatchError
from hcad.core.table import Table
from hcad.engine.codec import RowCodec
from hcad.engine.file import HCADFile


class TestStreamingAndDeletion(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.cols = [
            Column(0, 'i'),
            Column(1, 'd'),
            Column(2, '4s'),
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_codec_single_row_encode_decode(self):
        codec = RowCodec(self.cols)
        row = [42, 3.14159, b'test']
        packed = codec.encode_single_row(row)
        self.assertEqual(len(packed), codec.row_byte_size)

        decoded = codec.decode_single_row(packed)
        self.assertEqual(decoded[0], 42)
        self.assertAlmostEqual(decoded[1], 3.14159, places=4)
        self.assertEqual(decoded[2], b'test')

        # Test string auto-encode
        row_str = [42, 3.14159, 'test']
        packed_str = codec.encode_single_row(row_str)
        self.assertEqual(packed_str, packed)

        # Test length mismatch
        with self.assertRaises(SchemaMismatchError):
            codec.encode_single_row([42, 3.14])

        # Test corrupted byte length
        with self.assertRaises(CorruptedFileError):
            codec.decode_single_row(packed[:-1])

    def test_read_row_random_access_uncompressed(self):
        file_path = self.dir_path / "test_random_access.hcad"
        hfile = HCADFile.create(file_path, self.cols, compression=COMPRESSION_NONE)
        
        rows = [
            [i, float(i) * 1.5, f"r{i:03d}".encode('utf-8')]
            for i in range(20)
        ]
        hfile.append_rows(rows)

        # Read specific rows
        self.assertEqual(hfile.read_row(0)[0], 0)
        self.assertEqual(hfile.read_row(10)[0], 10)
        self.assertEqual(hfile.read_row(19)[0], 19)
        self.assertEqual(hfile.read_row(10)[2], b"r010")

        # Test index out of range
        with self.assertRaises(IndexError):
            hfile.read_row(-1)
        with self.assertRaises(IndexError):
            hfile.read_row(20)

    def test_read_row_compressed(self):
        file_path = self.dir_path / "test_random_access_comp.hcad"
        hfile = HCADFile.create(file_path, self.cols, compression=COMPRESSION_ZLIB)
        
        rows = [[i, float(i), b'test'] for i in range(10)]
        hfile.append_rows(rows)

        self.assertEqual(hfile.read_row(5)[0], 5)
        with self.assertRaises(IndexError):
            hfile.read_row(10)

    def test_read_range_uncompressed(self):
        file_path = self.dir_path / "test_range.hcad"
        hfile = HCADFile.create(file_path, self.cols, compression=COMPRESSION_NONE)
        
        rows = [[i, float(i), b'data'] for i in range(50)]
        hfile.append_rows(rows)

        # Normal slice
        tbl = hfile.read_range(10, 20)
        self.assertEqual(len(tbl), 10)
        self.assertEqual(tbl.rows[0][0], 10)
        self.assertEqual(tbl.rows[-1][0], 19)

        # Out of bounds start/end clamped
        tbl_edge = hfile.read_range(-5, 5)
        self.assertEqual(len(tbl_edge), 5)
        self.assertEqual(tbl_edge.rows[0][0], 0)
        self.assertEqual(tbl_edge.rows[-1][0], 4)

        tbl_end = hfile.read_range(45, 100)
        self.assertEqual(len(tbl_end), 5)
        self.assertEqual(tbl_end.rows[0][0], 45)
        self.assertEqual(tbl_end.rows[-1][0], 49)

        # Empty slice
        tbl_empty = hfile.read_range(20, 10)
        self.assertEqual(len(tbl_empty), 0)

    def test_read_range_compressed(self):
        file_path = self.dir_path / "test_range_comp.hcad"
        hfile = HCADFile.create(file_path, self.cols, compression=COMPRESSION_ZLIB)
        rows = [[i, float(i), b'data'] for i in range(20)]
        hfile.append_rows(rows)

        tbl = hfile.read_range(5, 12)
        self.assertEqual(len(tbl), 7)
        self.assertEqual(tbl.rows[0][0], 5)
        self.assertEqual(tbl.rows[-1][0], 11)

    def test_iter_rows_uncompressed(self):
        file_path = self.dir_path / "test_iter.hcad"
        hfile = HCADFile.create(file_path, self.cols, compression=COMPRESSION_NONE)
        rows = [[i, float(i), b'iter'] for i in range(100)]
        hfile.append_rows(rows)

        # Stream with batch_size smaller than total
        streamed = list(hfile.iter_rows(batch_size=17))
        self.assertEqual(len(streamed), 100)
        self.assertEqual(streamed[0][0], 0)
        self.assertEqual(streamed[-1][0], 99)

        # Stream with batch_size=1
        streamed_single = list(hfile.iter_rows(batch_size=1))
        self.assertEqual(len(streamed_single), 100)

        # Stream with batch_size > total
        streamed_large = list(hfile.iter_rows(batch_size=1000))
        self.assertEqual(len(streamed_large), 100)

        # Invalid batch_size
        with self.assertRaises(ValueError):
            list(hfile.iter_rows(batch_size=0))
        with self.assertRaises(ValueError):
            list(hfile.iter_rows(batch_size=-1))

    def test_iter_rows_compressed(self):
        file_path = self.dir_path / "test_iter_comp.hcad"
        hfile = HCADFile.create(file_path, self.cols, compression=COMPRESSION_ZLIB)
        rows = [[i, float(i), b'iter'] for i in range(25)]
        hfile.append_rows(rows)

        streamed = list(hfile.iter_rows(batch_size=5))
        self.assertEqual(len(streamed), 25)
        self.assertEqual(streamed[10][0], 10)

    def test_iter_empty_file(self):
        file_path = self.dir_path / "test_iter_empty.hcad"
        hfile = HCADFile.create(file_path, self.cols, compression=COMPRESSION_NONE)
        streamed = list(hfile.iter_rows(batch_size=10))
        self.assertEqual(len(streamed), 0)

    def test_delete_row_in_place_shift(self):
        file_path = self.dir_path / "test_delete_shift.hcad"
        hfile = HCADFile.create(file_path, self.cols, compression=COMPRESSION_NONE)
        
        # 1000 rows to test multi-chunk shift (buffer is 64KB, row is 16 bytes, so >4096 rows for multi-chunk)
        # Let's create 5000 rows so that total data bytes = 5000 * 16 = 80,000 bytes > 65536 chunk_size
        row_count = 5000
        rows = [[i, float(i), b'xdel'] for i in range(row_count)]
        hfile.append_rows(rows)

        initial_size = file_path.stat().st_size
        row_size = hfile.row_byte_size

        # 1. Delete middle row (row 2500)
        hfile.delete_row(2500)
        self.assertEqual(hfile.row_count, row_count - 1)
        self.assertEqual(file_path.stat().st_size, initial_size - row_size)

        # Verify row 2500 is now what was formerly row 2501
        self.assertEqual(hfile.read_row(2500)[0], 2501)
        self.assertEqual(hfile.read_row(2499)[0], 2499)

        # 2. Delete the first row (row 0)
        hfile.delete_row(0)
        self.assertEqual(hfile.row_count, row_count - 2)
        self.assertEqual(file_path.stat().st_size, initial_size - 2 * row_size)
        self.assertEqual(hfile.read_row(0)[0], 1)

        # 3. Delete terminal row
        last_idx = hfile.row_count - 1
        last_val = hfile.read_row(last_idx)[0]
        self.assertEqual(last_val, 4999)
        hfile.delete_row(last_idx)
        self.assertEqual(hfile.row_count, row_count - 3)
        self.assertEqual(file_path.stat().st_size, initial_size - 3 * row_size)
        self.assertEqual(hfile.read_row(hfile.row_count - 1)[0], 4998)

    def test_sync_parameter(self):
        file_path = self.dir_path / "test_sync.hcad"
        hfile = HCADFile.create(file_path, self.cols, compression=COMPRESSION_NONE)
        
        # Test append_row with sync=True
        hfile.append_row([1, 1.0, b'sync'], sync=True)
        self.assertEqual(hfile.row_count, 1)

        # Test append_rows with sync=True
        hfile.append_rows([[2, 2.0, b'sync'], [3, 3.0, b'sync']], sync=True)
        self.assertEqual(hfile.row_count, 3)

        # Test update_cell with sync=True
        hfile.update_cell(0, 0, 999, sync=True)
        self.assertEqual(hfile.read_row(0)[0], 999)

        # Test delete_row with sync=True
        hfile.delete_row(0, sync=True)
        self.assertEqual(hfile.row_count, 2)
        self.assertEqual(hfile.read_row(0)[0], 2)


if __name__ == '__main__':
    unittest.main()
