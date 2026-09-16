"""
HCAD Core components: constants, exceptions, columns, header, and table.
"""
from .constants import (
    IDENTIFIER,
    CURRENT_VERSION,
    VERSION_1,
    COMPRESSION_NONE,
    COMPRESSION_ZLIB,
    HEADER_FORMAT_V2,
    HEADER_SIZE_V2,
    HEADER_FORMAT_V1,
    HEADER_SIZE_V1,
    DEFAULT_MAX_DESCRIPTOR_SIZE,
)
from .exceptions import (
    HCADError,
    InvalidHeaderError,
    CorruptedFileError,
    SchemaMismatchError,
    UnsupportedVersionError,
    UnsupportedCompressionError,
)
from .column import Column
from .header import Header
from .table import Table

__all__ = [
    'IDENTIFIER',
    'CURRENT_VERSION',
    'VERSION_1',
    'COMPRESSION_NONE',
    'COMPRESSION_ZLIB',
    'HEADER_FORMAT_V2',
    'HEADER_SIZE_V2',
    'HEADER_FORMAT_V1',
    'HEADER_SIZE_V1',
    'DEFAULT_MAX_DESCRIPTOR_SIZE',
    'HCADError',
    'InvalidHeaderError',
    'CorruptedFileError',
    'SchemaMismatchError',
    'UnsupportedVersionError',
    'UnsupportedCompressionError',
    'Column',
    'Header',
    'Table',
]
