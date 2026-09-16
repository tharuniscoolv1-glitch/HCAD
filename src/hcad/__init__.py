"""
HCAD: Highly Compressed Activity Data
A lightweight, high-performance binary tabular format for activity and time-series data.
"""
from .core.constants import (
    IDENTIFIER,
    CURRENT_VERSION,
    COMPRESSION_NONE,
    COMPRESSION_ZLIB,
)
from .core.exceptions import (
    HCADError,
    InvalidHeaderError,
    CorruptedFileError,
    SchemaMismatchError,
    UnsupportedVersionError,
    UnsupportedCompressionError,
)
from .core.column import Column
from .core.header import Header
from .core.table import Table
from .engine.file import HCADFile

__version__ = "0.1.0"

__all__ = [
    'HCADFile',
    'Table',
    'Column',
    'Header',
    'IDENTIFIER',
    'CURRENT_VERSION',
    'COMPRESSION_NONE',
    'COMPRESSION_ZLIB',
    'HCADError',
    'InvalidHeaderError',
    'CorruptedFileError',
    'SchemaMismatchError',
    'UnsupportedVersionError',
    'UnsupportedCompressionError',
]
