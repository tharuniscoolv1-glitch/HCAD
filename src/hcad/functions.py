"""
Procedural API for HCAD files.
Provides convenient procedural functions backed by the high-performance HCAD engine.
"""
import os
import struct
import zlib
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from .core.constants import (
    IDENTIFIER,
    CURRENT_VERSION,
    COMPRESSION_NONE,
    COMPRESSION_ZLIB,
    DEFAULT_MAX_DESCRIPTOR_SIZE,
    HEADER_FORMAT_V2,
    HEADER_SIZE_V1,
    HEADER_SIZE_V2,
)
from .core.column import Column
from .core.header import Header
from .core.table import Table
from .core.exceptions import (
    HCADError,
    InvalidHeaderError,
    CorruptedFileError,
    SchemaMismatchError,
    UnsupportedCompressionError,
)
from .engine.file import HCADFile

# Export standard constants
VERSION = CURRENT_VERSION
MAX_COLUMN_DESCRIPTOR_SIZE = DEFAULT_MAX_DESCRIPTOR_SIZE
COMPRESSION = COMPRESSION_NONE
HEADERFORMAT = HEADER_FORMAT_V2
HEADERSIZE = HEADER_SIZE_V2


def _readMetadata(filePath: str) -> Tuple[int, int, int, int, List[str], int]:
    """
    Internal helper to validate and read the HCAD file header and column descriptors.
    Returns:
        (numberOfColumns, version, compression, maxColumnDescriptorSize, descriptions, dataOffset)
    Raises:
        ValueError if the file is not a valid HCAD file or cannot be parsed.
    """
    try:
        hf = HCADFile.open(filePath)
        descriptions = [col.descriptor for col in hf.columns]
        return (
            hf.header.column_count,
            hf.header.version,
            hf.header.compression,
            hf.header.max_descriptor_size,
            descriptions,
            hf.data_offset,
        )
    except (HCADError, OSError, ValueError) as e:
        raise ValueError(f"Invalid HCAD file: {e}") from e


def validateFile(filePath: str) -> bool:
    """
    Validates whether the given file is a valid HCAD file.
    Performs full integrity validation (header, column descriptors, and data payload).
    Returns True if valid, False otherwise without raising uncaught exceptions.
    """
    try:
        hf = HCADFile.open(filePath)
        hf.read()
        return True
    except Exception:
        return False


def getCompressionFromFile(filePath: str) -> int:
    """
    Returns the compression flag from the HCAD file header.
    0 = Uncompressed, 1 = zlib compressed.
    """
    try:
        hf = HCADFile.open(filePath)
        return hf.header.compression
    except Exception as e:
        raise ValueError("Invalid HCAD file.") from e


def getColumnDescriptions(filePath: str) -> Tuple[int, List[str]]:
    """
    Returns the number of columns and the list of column descriptor format strings.
    """
    try:
        hf = HCADFile.open(filePath)
        descriptions = [col.descriptor for col in hf.columns]
        return hf.header.column_count, descriptions
    except Exception as e:
        raise ValueError("Invalid HCAD file.") from e


def makeColumnDescriptorsBytes(
    numberOfColumns: int,
    descriptors: Union[List[str], Tuple[str, ...], Dict[int, str]],
    maxColumnDescriptorSize: int,
) -> bytes:
    """
    Validates and encodes column descriptor strings into binary bytes format.
    Format per column: uint16 column_id + uint16 description_length + UTF-8 description bytes.
    """
    if numberOfColumns < 0:
        raise ValueError(f"Number of columns cannot be negative: {numberOfColumns}")

    if isinstance(descriptors, dict):
        expected_keys = set(range(numberOfColumns))
        actual_keys = set(descriptors.keys())
        if actual_keys != expected_keys:
            raise ValueError(
                f"Descriptors dictionary keys {sorted(actual_keys)} do not match expected 0..{numberOfColumns-1} range."
            )
        desc_list = [descriptors[i] for i in range(numberOfColumns)]
    elif isinstance(descriptors, (list, tuple)):
        desc_list = list(descriptors)
    else:
        raise ValueError(f"Expected descriptors to be a list, tuple, or dict, got {type(descriptors).__name__}")

    if len(desc_list) != numberOfColumns:
        raise ValueError(
            f"Expected {numberOfColumns} descriptors, but received {len(desc_list)}."
        )

    buf = bytearray()
    for col_id in range(numberOfColumns):
        col = Column(col_id, desc_list[col_id], max_descriptor_size=maxColumnDescriptorSize)
        buf.extend(col.to_bytes())

    return bytes(buf)


def createNewFile(
    fileName: str,
    path: str,
    info: List[str],
    maxColumnDescriptorSize: int = DEFAULT_MAX_DESCRIPTOR_SIZE,
    compression: int = COMPRESSION_NONE,
) -> None:
    """
    Creates a new HCAD file with the given column format descriptions.
    """
    if compression not in (COMPRESSION_NONE, COMPRESSION_ZLIB):
        raise ValueError(f"Unsupported compression format: {compression}")

    folder = path if path else "."
    target_path = os.path.join(folder, fileName)

    columns = [
        Column(col_id=idx, descriptor=desc, max_descriptor_size=maxColumnDescriptorSize)
        for idx, desc in enumerate(info)
    ]

    try:
        HCADFile.create(
            file_path=target_path,
            columns=columns,
            max_descriptor_size=maxColumnDescriptorSize,
            compression=compression,
            overwrite=True,
        )
    except (HCADError, ValueError) as e:
        raise ValueError(f"Failed to create HCAD file: {e}") from e


def writeDataToFile(filePath: str, data: dict) -> None:
    """
    Writes or appends data to an HCAD file.
    data format:
    {
        'numberOfColumns': int,
        'descriptions': list of str,
        'payload': {column_index: [values]}
    }
    """
    try:
        hf = HCADFile.open(filePath)
    except Exception as e:
        raise ValueError("Invalid HCAD file.") from e

    if not isinstance(data, dict):
        raise ValueError("Data must be a dictionary.")

    for req in ('numberOfColumns', 'descriptions', 'payload'):
        if req not in data:
            raise ValueError(f"Data dictionary must contain 'numberOfColumns', 'descriptions', and 'payload'.")

    if data['numberOfColumns'] != hf.header.column_count:
        raise ValueError("Number of columns in data does not match the number of columns in the file.")

    if len(data['descriptions']) != hf.header.column_count:
        raise ValueError("Length of descriptions in data does not match the number of columns in the file.")

    for i in range(hf.header.column_count):
        file_desc = hf.columns[i].descriptor
        data_desc = data['descriptions'][i].strip().lstrip('<')
        if file_desc != data_desc:
            raise ValueError(f"Description for column {i} does not match the description in the file.")

    payload = data['payload']
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a dictionary.")

    if len(payload) != hf.header.column_count:
        raise ValueError("Payload does not contain data for all columns.")

    try:
        table = Table.from_dict(hf.columns, payload)
        if len(table) == 0:
            return
        hf.append_rows(table.rows)
    except (HCADError, ValueError, IndexError) as e:
        raise ValueError(f"Failed to write data to HCAD file: {e}") from e


def readDataFromFile(filePath: str) -> Dict[int, List[Any]]:
    """
    Reads and returns all row data from the HCAD file as a dictionary:
    {column_index: [values]}
    """
    try:
        hf = HCADFile.open(filePath)
        table = hf.read()
        return table.to_dict()
    except (HCADError, ValueError, OSError) as e:
        raise ValueError(f"Invalid HCAD file: {e}") from e


def compressDataInFile(filePath: str) -> None:
    """
    Compresses an uncompressed HCAD file in place using zlib.
    """
    try:
        hf = HCADFile.open(filePath)
        hf.compress()
    except (HCADError, ValueError, OSError) as e:
        raise ValueError(f"Failed to compress file: {e}") from e


def decompressDataInFile(filePath: str) -> None:
    """
    Decompresses a compressed HCAD file in place.
    """
    try:
        hf = HCADFile.open(filePath)
        hf.decompress()
    except (HCADError, ValueError, OSError) as e:
        raise ValueError(f"Failed to decompress file: {e}") from e
