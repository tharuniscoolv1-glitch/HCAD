"""
Tests for HCAD Header packing, unpacking, and validation.
"""
import io
import unittest

from src.hcad.core.constants import (
    IDENTIFIER,
    CURRENT_VERSION,
    COMPRESSION_NONE,
    COMPRESSION_ZLIB,
    HEADER_SIZE_V2,
)
from src.hcad.core.header import Header
from src.hcad.core.exceptions import (
    InvalidHeaderError,
    UnsupportedVersionError,
    UnsupportedCompressionError,
)


class TestHeader(unittest.TestCase):

    def test_pack_and_unpack_v2(self):
        header = Header(
            column_count=5,
            max_descriptor_size=16,
            version=CURRENT_VERSION,
            compression=COMPRESSION_ZLIB,
            row_count=1234,
        )
        packed = header.pack()
        self.assertEqual(len(packed), HEADER_SIZE_V2)

        stream = io.BytesIO(packed)
        unpacked_header, size = Header.from_stream(stream)

        self.assertEqual(size, HEADER_SIZE_V2)
        self.assertEqual(unpacked_header.column_count, 5)
        self.assertEqual(unpacked_header.max_descriptor_size, 16)
        self.assertEqual(unpacked_header.version, CURRENT_VERSION)
        self.assertEqual(unpacked_header.compression, COMPRESSION_ZLIB)
        self.assertEqual(unpacked_header.row_count, 1234)

    def test_invalid_identifier(self):
        bad_stream = io.BytesIO(b'BADMAGIC' + b'\x00' * (HEADER_SIZE_V2 - 8))
        with self.assertRaises(InvalidHeaderError):
            Header.from_stream(bad_stream)

    def test_unsupported_version(self):
        with self.assertRaises(UnsupportedVersionError):
            Header(column_count=1, version=99)

    def test_unsupported_compression(self):
        with self.assertRaises(UnsupportedCompressionError):
            Header(column_count=1, compression=99)

    def test_invalid_bounds(self):
        with self.assertRaises(InvalidHeaderError):
            Header(column_count=-1)
        with self.assertRaises(InvalidHeaderError):
            Header(column_count=1, max_descriptor_size=0)
        with self.assertRaises(InvalidHeaderError):
            Header(column_count=1, row_count=-5)


if __name__ == '__main__':
    unittest.main()
