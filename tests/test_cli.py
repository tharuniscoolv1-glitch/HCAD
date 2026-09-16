import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from hcad.cli import main
from hcad.core.column import Column
from hcad.core.constants import COMPRESSION_NONE, COMPRESSION_ZLIB
from hcad.core.table import Table
from hcad.engine.file import HCADFile


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.hcad_file = self.dir_path / "cli_sample.hcad"

        cols = [
            Column(0, 'i'),
            Column(1, 'd'),
            Column(2, '4s'),
        ]
        rows = [
            [1, 1.5, b'r001'],
            [2, 2.5, b'r002'],
            [3, 3.5, b'r003'],
            [4, 4.5, b'r004'],
            [5, 5.5, b'r005'],
        ]
        hfile = HCADFile.create(self.hcad_file, cols, compression=COMPRESSION_NONE)
        hfile.append_rows(rows)

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, *args):
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            code = main(list(args))
        return code, stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_cli_help(self):
        code, out, err = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("HCAD", out)

    def test_cli_info(self):
        code, out, err = self.run_cli("info", str(self.hcad_file))
        self.assertEqual(code, 0)
        self.assertIn("Row Count:       5", out)
        self.assertIn("Column Count:    3", out)
        self.assertIn("uncompressed", out)

        # Test non-existent file
        code, out, err = self.run_cli("info", str(self.dir_path / "missing.hcad"))
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_cli_validate(self):
        code, out, err = self.run_cli("validate", str(self.hcad_file))
        self.assertEqual(code, 0)
        self.assertIn("VALID", out)

        # Test corrupted file
        corrupt_file = self.dir_path / "corrupt.hcad"
        corrupt_file.write_bytes(b"NOT_AN_HCAD_FILE_AT_ALL")
        code, out, err = self.run_cli("validate", str(corrupt_file))
        self.assertEqual(code, 1)
        self.assertIn("INVALID", err)

    def test_cli_dump_table(self):
        code, out, err = self.run_cli("dump", str(self.hcad_file), "--limit", "2")
        self.assertEqual(code, 0)
        self.assertIn("Dumping 2 row(s)", out)
        self.assertIn("r001", out)
        self.assertIn("r002", out)

    def test_cli_dump_json(self):
        code, out, err = self.run_cli("dump", str(self.hcad_file), "--format", "json", "--limit", "3")
        self.assertEqual(code, 0)
        parsed = json.loads(out)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["0"], 1)

    def test_cli_dump_csv(self):
        code, out, err = self.run_cli("dump", str(self.hcad_file), "--format", "csv")
        self.assertEqual(code, 0)
        self.assertIn("col_0,col_1,col_2", out)
        self.assertIn("1,1.5,r001", out)

    def test_cli_compress_and_decompress(self):
        # Compress
        code, out, err = self.run_cli("compress", str(self.hcad_file))
        self.assertEqual(code, 0)
        self.assertIn("Successfully compressed", out)

        hf = HCADFile.open(self.hcad_file)
        self.assertTrue(hf.is_compressed)

        # Decompress
        code, out, err = self.run_cli("decompress", str(self.hcad_file))
        self.assertEqual(code, 0)
        self.assertIn("Successfully decompressed", out)

        hf = HCADFile.open(self.hcad_file)
        self.assertFalse(hf.is_compressed)

    def test_cli_export_csv_and_json(self):
        csv_out = self.dir_path / "cli_exported.csv"
        code, out, err = self.run_cli("export", str(self.hcad_file), "--format", "csv", "-o", str(csv_out))
        self.assertEqual(code, 0)
        self.assertTrue(csv_out.exists())
        self.assertIn("1,1.5,r001", csv_out.read_text())

        json_out = self.dir_path / "cli_exported.json"
        code, out, err = self.run_cli("export", str(self.hcad_file), "--format", "json", "-o", str(json_out))
        self.assertEqual(code, 0)
        self.assertTrue(json_out.exists())

    def test_cli_export_stdout(self):
        code, out, err = self.run_cli("export", str(self.hcad_file), "--format", "csv")
        self.assertEqual(code, 0)
        self.assertIn("1,1.5,r001", out)

    def test_cli_import_csv(self):
        csv_file = self.dir_path / "input.csv"
        csv_file.write_text("col_0,col_1,col_2\n10,10.5,test\n20,20.5,data\n")

        hcad_out = self.dir_path / "from_cli.hcad"
        code, out, err = self.run_cli(
            "import", str(csv_file),
            "-o", str(hcad_out),
            "--columns", "0:i,1:d,2:4s",
            "--compress",
        )
        self.assertEqual(code, 0)
        self.assertTrue(hcad_out.exists())

        hf = HCADFile.open(hcad_out)
        self.assertTrue(hf.is_compressed)
        self.assertEqual(hf.row_count, 2)
        self.assertEqual(hf.read_row(0)[0], 10)


if __name__ == '__main__':
    unittest.main()
