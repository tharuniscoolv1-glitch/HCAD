"""
HCAD Command-Line Interface (CLI).
Zero-dependency command-line utility for inspecting, validating, converting,
and transforming HCAD binary files.
"""
import argparse
import io
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from .core.constants import COMPRESSION_NONE, COMPRESSION_ZLIB
from .core.column import Column
from .core.exceptions import HCADError
from .core.table import Table
from .engine.file import HCADFile


def _parse_column_specs(specs_str: str) -> List[Column]:
    """
    Parses column specification strings.
    Format examples:
      "0:i,1:d,2:4s"
      "i,d,4s" (auto-assigns IDs 0, 1, 2)
    """
    columns = []
    tokens = [t.strip() for t in specs_str.split(',') if t.strip()]
    for idx, token in enumerate(tokens):
        if ':' in token:
            parts = token.split(':', 1)
            col_id = int(parts[0].strip())
            desc = parts[1].strip()
        else:
            col_id = idx
            desc = token
        columns.append(Column(col_id, desc))
    return columns


def cmd_info(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"Error: File not found: {path}\n")
        return 1

    try:
        hf = HCADFile.open(path)
    except Exception as e:
        sys.stderr.write(f"Error reading HCAD metadata: {e}\n")
        return 1

    file_size = path.stat().st_size
    comp_str = "ZLIB (compressed)" if hf.header.compression == COMPRESSION_ZLIB else "None (uncompressed)"

    print("HCAD File Metadata:")
    print("=" * 50)
    print(f"Path:            {path.resolve()}")
    print(f"File Size:       {file_size:,} bytes")
    print(f"Version:         {hf.header.version}")
    print(f"Compression:     {comp_str}")
    print(f"Row Count:       {hf.header.row_count:,}")
    print(f"Column Count:    {len(hf.columns)}")
    print(f"Row Byte Size:   {hf.row_byte_size} bytes")
    print(f"Data Offset:     {hf.data_offset} bytes")
    print("\nColumns:")
    for idx, col in enumerate(hf.columns):
        print(f"  [{idx}] ID: {col.id:<5} Descriptor: '{col.descriptor}' ({col.byte_size} bytes, {col.field_count} field(s))")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"Error: File not found: {path}\n")
        return 1

    try:
        hf = HCADFile.open(path)
        table = hf.read()
        print(f"VALID: '{path}' is a valid HCAD file ({len(table)} rows, {len(hf.columns)} columns).")
        return 0
    except Exception as e:
        sys.stderr.write(f"INVALID: '{path}' failed integrity validation: {e}\n")
        return 1


def cmd_dump(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"Error: File not found: {path}\n")
        return 1

    try:
        hf = HCADFile.open(path)
    except Exception as e:
        sys.stderr.write(f"Error opening HCAD file: {e}\n")
        return 1

    total_rows = hf.row_count
    offset = max(0, args.offset)
    limit = args.limit if args.limit is not None and args.limit >= 0 else total_rows
    end = min(total_rows, offset + limit)

    if offset >= total_rows or offset >= end:
        rows = []
    else:
        table_slice = hf.read_range(offset, end)
        rows = table_slice.rows

    if args.format == "json":
        sub_table = Table(hf.columns, rows)
        print(sub_table.to_json(orient="records", indent=2))
        return 0

    if args.format == "csv":
        sub_table = Table(hf.columns, rows)
        buf = io.StringIO()
        sub_table.to_csv(buf)
        sys.stdout.write(buf.getvalue())
        return 0

    # Default table output
    headers = [f"Col {col.id} ({col.descriptor})" for col in hf.columns]
    print(f"--- Dumping {len(rows)} row(s) [offset {offset}..{end}] of {total_rows} total ---")
    header_line = " | ".join(headers)
    print(header_line)
    print("-" * max(len(header_line), 40))

    for row_idx, row in enumerate(rows, start=offset):
        formatted_vals = []
        for val in row:
            if isinstance(val, bytes):
                try:
                    formatted_vals.append(val.decode('utf-8').rstrip('\x00'))
                except UnicodeDecodeError:
                    formatted_vals.append(str(val))
            else:
                formatted_vals.append(str(val))
        print(f"[{row_idx}] " + " | ".join(formatted_vals))

    return 0


def cmd_compress(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"Error: File not found: {path}\n")
        return 1

    try:
        hf = HCADFile.open(path)
        hf.compress()
        print(f"Successfully compressed '{path}'.")
        return 0
    except Exception as e:
        sys.stderr.write(f"Compression failed: {e}\n")
        return 1


def cmd_decompress(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"Error: File not found: {path}\n")
        return 1

    try:
        hf = HCADFile.open(path)
        hf.decompress()
        print(f"Successfully decompressed '{path}'.")
        return 0
    except Exception as e:
        sys.stderr.write(f"Decompression failed: {e}\n")
        return 1


def cmd_export(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"Error: File not found: {path}\n")
        return 1

    fmt = args.format.lower()
    out_target = args.output

    try:
        hf = HCADFile.open(path)
        if out_target is None or out_target == "-":
            # Output to stdout
            buf = io.StringIO()
            if fmt == "csv":
                tbl = hf.read()
                tbl.to_csv(buf)
            elif fmt == "json":
                buf.write(hf.to_json(orient="records", indent=2))
            else:
                sys.stderr.write(f"Error: Unsupported export format '{fmt}'. Choose 'csv' or 'json'.\n")
                return 1
            sys.stdout.write(buf.getvalue())
        else:
            out_path = Path(out_target)
            if fmt == "csv":
                hf.to_csv(out_path)
            elif fmt == "json":
                hf.to_json(out_path, orient="records", indent=2)
            else:
                sys.stderr.write(f"Error: Unsupported export format '{fmt}'. Choose 'csv' or 'json'.\n")
                return 1
            print(f"Successfully exported '{path}' to '{out_path}' ({fmt.upper()}).")
        return 0
    except Exception as e:
        sys.stderr.write(f"Export failed: {e}\n")
        return 1


def cmd_import(args: argparse.Namespace) -> int:
    in_path = Path(args.input)
    if not in_path.exists():
        sys.stderr.write(f"Error: Input file not found: {in_path}\n")
        return 1

    out_path = Path(args.output)
    fmt = args.format.lower()
    compression = COMPRESSION_ZLIB if args.compress else COMPRESSION_NONE

    columns = None
    if args.columns:
        try:
            columns = _parse_column_specs(args.columns)
        except Exception as e:
            sys.stderr.write(f"Error parsing columns specification: {e}\n")
            return 1

    try:
        if fmt == "csv":
            if not columns:
                sys.stderr.write("Error: --columns specification is required for CSV import (e.g. --columns '0:i,1:d,2:4s').\n")
                return 1
            HCADFile.from_csv(
                file_path=out_path,
                csv_path=in_path,
                columns=columns,
                compression=compression,
                overwrite=args.overwrite,
            )
        elif fmt == "json":
            HCADFile.from_json(
                file_path=out_path,
                json_path_or_str=in_path,
                columns=columns,
                compression=compression,
                overwrite=args.overwrite,
            )
        else:
            sys.stderr.write(f"Error: Unsupported format '{fmt}'. Choose 'csv' or 'json'.\n")
            return 1

        print(f"Successfully imported '{in_path}' to HCAD file '{out_path}'.")
        return 0
    except Exception as e:
        sys.stderr.write(f"Import failed: {e}\n")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hcad",
        description="HCAD (Highly Compressed Activity Data) CLI tool.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # info
    p_info = subparsers.add_parser("info", help="Display metadata and schema of an HCAD file")
    p_info.add_argument("file", help="Path to the HCAD file")

    # validate
    p_val = subparsers.add_parser("validate", help="Validate HCAD file integrity")
    p_val.add_argument("file", help="Path to the HCAD file")

    # dump
    p_dump = subparsers.add_parser("dump", help="Print table rows to stdout")
    p_dump.add_argument("file", help="Path to the HCAD file")
    p_dump.add_argument("--offset", type=int, default=0, help="Row offset to start dumping from")
    p_dump.add_argument("--limit", type=int, default=20, help="Maximum number of rows to dump (-1 for all)")
    p_dump.add_argument("--format", choices=["table", "csv", "json"], default="table", help="Output format")

    # compress
    p_comp = subparsers.add_parser("compress", help="Compress an uncompressed HCAD file in place")
    p_comp.add_argument("file", help="Path to the HCAD file")

    # decompress
    p_decomp = subparsers.add_parser("decompress", help="Decompress a compressed HCAD file in place")
    p_decomp.add_argument("file", help="Path to the HCAD file")

    # export
    p_exp = subparsers.add_parser("export", help="Export HCAD file to CSV or JSON")
    p_exp.add_argument("file", help="Path to the HCAD file")
    p_exp.add_argument("--format", choices=["csv", "json"], default="csv", help="Target export format")
    p_exp.add_argument("-o", "--output", help="Destination path (defaults to stdout if omitted or '-')")

    # import
    p_imp = subparsers.add_parser("import", help="Import CSV or JSON to an HCAD file")
    p_imp.add_argument("input", help="Path to input CSV or JSON file")
    p_imp.add_argument("-o", "--output", required=True, help="Path to output HCAD file")
    p_imp.add_argument("--format", choices=["csv", "json"], default="csv", help="Input format")
    p_imp.add_argument("--columns", help="Column specifications (e.g. '0:i,1:d,2:4s')")
    p_imp.add_argument("--compress", action="store_true", help="Store output with zlib compression")
    p_imp.add_argument("--overwrite", action="store_true", default=True, help="Overwrite output file if exists")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "info": cmd_info,
        "validate": cmd_validate,
        "dump": cmd_dump,
        "compress": cmd_compress,
        "decompress": cmd_decompress,
        "export": cmd_export,
        "import": cmd_import,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
