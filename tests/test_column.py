"""
Tests for HCAD Column definition, compound formats, and struct packing/unpacking.
"""
import io
import unittest

from hcad.core.column import Column
from hcad.core.exceptions import SchemaMismatchError, CorruptedFileError


class TestColumn(unittest.TestCase):

    def test_single_value_column(self):
        col = Column(col_id=0, descriptor='i')
        self.assertEqual(col.id, 0)
        self.assertEqual(col.byte_size, 4)
        self.assertEqual(col.field_count, 1)

        packed = col.pack(42)
        self.assertEqual(col.unpack(packed), 42)

    def test_compound_column_types(self):
        # Format: 'H h H' (3 unsigned/signed shorts)
        col = Column(col_id=1, descriptor='H h H')
        self.assertEqual(col.byte_size, 6)
        self.assertEqual(col.field_count, 3)

        packed = col.pack((100, -50, 300))
        self.assertEqual(col.unpack(packed), (100, -50, 300))

        # Format: 'c i' (1 char, 1 int)
        col2 = Column(col_id=2, descriptor='c i')
        self.assertEqual(col2.byte_size, 5)
        self.assertEqual(col2.field_count, 2)

        packed2 = col2.pack((b'X', 9999))
        self.assertEqual(col2.unpack(packed2), (b'X', 9999))

    def test_string_conversion(self):
        col = Column(col_id=3, descriptor='5s')
        self.assertEqual(col.byte_size, 5)
        # Pass python str, should auto-encode
        packed = col.pack('hello')
        self.assertEqual(col.unpack(packed), b'hello')

    def test_invalid_descriptor(self):
        with self.assertRaises(SchemaMismatchError):
            Column(col_id=0, descriptor='')
        with self.assertRaises(SchemaMismatchError):
            Column(col_id=0, descriptor='invalid_fmt_xyz')
        with self.assertRaises(SchemaMismatchError):
            Column(col_id=0, descriptor='>i')  # Disallowed big-endian prefix

    def test_stream_roundtrip(self):
        col = Column(col_id=42, descriptor='H h H')
        stream = io.BytesIO(col.to_bytes())
        unpacked_col = Column.from_stream(stream)
        self.assertEqual(col, unpacked_col)


if __name__ == '__main__':
    unittest.main()
