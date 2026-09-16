"""
Backwards-compatibility shim for functions.py.
Redirects to the canonical hcad.functions module.
"""
from .hcad.functions import (
    IDENTIFIER,
    VERSION,
    MAX_COLUMN_DESCRIPTOR_SIZE,
    COMPRESSION,
    HEADERFORMAT,
    HEADERSIZE,
    _readMetadata,
    validateFile,
    getCompressionFromFile,
    getColumnDescriptions,
    makeColumnDescriptorsBytes,
    createNewFile,
    writeDataToFile,
    readDataFromFile,
    compressDataInFile,
    decompressDataInFile,
)

__all__ = [
    'IDENTIFIER',
    'VERSION',
    'MAX_COLUMN_DESCRIPTOR_SIZE',
    'COMPRESSION',
    'HEADERFORMAT',
    'HEADERSIZE',
    '_readMetadata',
    'validateFile',
    'getCompressionFromFile',
    'getColumnDescriptions',
    'makeColumnDescriptorsBytes',
    'createNewFile',
    'writeDataToFile',
    'readDataFromFile',
    'compressDataInFile',
    'decompressDataInFile',
]
