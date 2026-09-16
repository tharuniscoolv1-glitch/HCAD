"""
HCAD (Highly Compressed Activity Data) Constants.
"""
import struct

# Magic 8-byte file identifier
IDENTIFIER = b'\x3A\x3B\x4C\x1E\xFF\xB4\xE9\xFF'

# Version constant
VERSION_1 = 1
CURRENT_VERSION = VERSION_1

# Compression flags
COMPRESSION_NONE = 0
COMPRESSION_ZLIB = 1
SUPPORTED_COMPRESSIONS = (COMPRESSION_NONE, COMPRESSION_ZLIB)

# Header format:
# - identifier: 8 bytes (<8s)
# - column_count: unsigned short (<H, 2 bytes)
# - max_column_descriptor_size: unsigned short (<H, 2 bytes)
# - version: unsigned short (<H, 2 bytes)
# - compression: unsigned short (<H, 2 bytes)
# - row_count: unsigned int (<I, 4 bytes)
# Total size = 8 + 2 + 2 + 2 + 2 + 4 = 20 bytes
HEADER_FORMAT_V2 = '<8s H H H H I'
HEADER_SIZE_V2 = struct.calcsize(HEADER_FORMAT_V2)  # 20 bytes

# Legacy Header format (16 bytes):
# identifier (8s), column_count (H), version (H), compression (H), max_desc_size (H)
HEADER_FORMAT_V1 = '<8s H H H H'
HEADER_SIZE_V1 = struct.calcsize(HEADER_FORMAT_V1)  # 16 bytes

DEFAULT_MAX_DESCRIPTOR_SIZE = 32
