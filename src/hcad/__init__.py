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
from .functions import (
    createNewFile,
    validateFile,
    getCompressionFromFile,
    getColumnDescriptions,
    makeColumnDescriptorsBytes,
    writeDataToFile,
    readDataFromFile,
    compressDataInFile,
    decompressDataInFile,
)

__version__ = "0.2.0"

__all__ = [
    # Core Classes
    'HCADFile',
    'Table',
    'Column',
    'Header',
    # Constants
    'IDENTIFIER',
    'CURRENT_VERSION',
    'COMPRESSION_NONE',
    'COMPRESSION_ZLIB',
    # Procedural Functions
    'createNewFile',
    'validateFile',
    'getCompressionFromFile',
    'getColumnDescriptions',
    'makeColumnDescriptorsBytes',
    'writeDataToFile',
    'readDataFromFile',
    'compressDataInFile',
    'decompressDataInFile',
    # Exceptions
    'HCADError',
    'InvalidHeaderError',
    'CorruptedFileError',
    'SchemaMismatchError',
    'UnsupportedVersionError',
    'UnsupportedCompressionError',
]
