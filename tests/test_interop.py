import io
import json
import tempfile
import unittest
from pathlib import Path

from hcad.core.column import Column
from hcad.core.constants import COMPRESSION_NONE, COMPRESSION_ZLIB
from hcad.core.exceptions import SchemaMismatchError
from hcad.core.table import Table
from hcad.engine.file import HCADFile


class TestInterop(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.cols = [
            Column(10, 'i'),      # Index 0, ID 10
            Column(0, 'd'),       # Index 1, ID 0
            Column(1, '4s'),      # Index 2, ID 1
        ]
        self.sample_rows = [
            [100, 1.25, b'test'],
            [200, 2.50, b'data'],
            [300, 3.75, b'hcad'],
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_column_disambiguation(self):
        table = Table(self.cols, self.sample_rows)

        # By index: index 0 is column with ID 10
        col_idx_0 = table.get_column_by_index(0)
        self.assertEqual(col_idx_0, [100, 200, 300])

        # By ID: ID 0 is column at index 1
        col_id_0 = table.get_column_by_id(0)
        self.assertEqual(col_id_0, [1.25, 2.50, 3.75])

        # get_column(0) should resolve ID 0
        self.assertEqual(table.get_column(0), [1.25, 2.50, 3.75])

        # get_column(10) resolves ID 10
        self.assertEqual(table.get_column(10), [100, 200, 300])

        # Invalid index / ID errors
        with self.assertRaises(IndexError):
            table.get_column_by_index(99)
        with self.assertRaises(SchemaMismatchError):
            table.get_column_by_id(99)

        # Cell updates by explicit ID and index
        table.update_cell_by_id(0, 10, 999)
        self.assertEqual(table.get_row(0)[0], 999)

        table.update_cell_by_index(0, 1, 9.99)
        self.assertEqual(table.get_row(0)[1], 9.99)

    def test_table_csv_roundtrip(self):
        table = Table(self.cols, self.sample_rows)
        csv_path = self.dir_path / "table.csv"

        # Export to CSV
        table.to_csv(csv_path)
        self.assertTrue(csv_path.exists())

        # Import from CSV
        imported = Table.from_csv(csv_path, self.cols)
        self.assertEqual(len(imported), len(table))
        self.assertEqual(imported.get_column_by_id(10), [100, 200, 300])
        self.assertEqual(imported.get_column_by_id(0), [1.25, 2.50, 3.75])
        self.assertEqual(imported.get_column_by_id(1), [b'test', b'data', b'hcad'])

    def test_csv_buffer_roundtrip(self):
        table = Table(self.cols, self.sample_rows)
        buf = io.StringIO()
        table.to_csv(buf)

        buf.seek(0)
        imported = Table.from_csv(buf, self.cols)
        self.assertEqual(len(imported), 3)
        self.assertEqual(imported.rows[1][0], 200)

    def test_hcad_file_csv_bridge(self):
        hcad_path = self.dir_path / "stream_bridge.hcad"
        hfile = HCADFile.create(hcad_path, self.cols, compression=COMPRESSION_NONE)
        hfile.append_rows(self.sample_rows)

        csv_path = self.dir_path / "exported.csv"
        hfile.to_csv(csv_path)
        self.assertTrue(csv_path.exists())

        # Create new HCAD file directly from CSV
        new_hcad_path = self.dir_path / "from_csv.hcad"
        imported_hfile = HCADFile.from_csv(new_hcad_path, csv_path, self.cols)
        self.assertEqual(imported_hfile.row_count, 3)
        self.assertEqual(imported_hfile.read_row(0)[0], 100)

    def test_table_json_records_orient(self):
        table = Table(self.cols, self.sample_rows)
        json_str = table.to_json(orient="records")
        parsed = json.loads(json_str)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["10"], 100)
        self.assertEqual(parsed[0]["0"], 1.25)
        self.assertEqual(parsed[0]["1"], "test")

        # Import back
        imported = Table.from_json(json_str, columns=self.cols)
        self.assertEqual(imported.rows[0][0], 100)

    def test_table_json_columns_orient(self):
        table = Table(self.cols, self.sample_rows)
        json_str = table.to_json(orient="columns")
        parsed = json.loads(json_str)
        self.assertIn("10", parsed)
        self.assertEqual(parsed["10"], [100, 200, 300])

        # Import back
        imported = Table.from_json(json_str, columns=self.cols)
        self.assertEqual(imported.get_column_by_id(10), [100, 200, 300])

    def test_table_json_split_orient_auto_schema(self):
        table = Table(self.cols, self.sample_rows)
        json_path = self.dir_path / "table.json"
        table.to_json(file_path=json_path, orient="split", indent=2)

        # Import back with auto schema inference from split JSON!
        imported = Table.from_json(json_path)
        self.assertEqual(len(imported.columns), 3)
        self.assertEqual(imported.columns[0].id, 10)
        self.assertEqual(imported.columns[0].descriptor, 'i')
        self.assertEqual(len(imported.rows), 3)
        self.assertEqual(imported.rows[0][0], 100)

    def test_hcad_file_json_bridge(self):
        hcad_path = self.dir_path / "file_json.hcad"
        hfile = HCADFile.create(hcad_path, self.cols)
        hfile.append_rows(self.sample_rows)

        json_path = self.dir_path / "exported.json"
        hfile.to_json(json_path, orient="split")

        # Import to new HCAD file
        new_hcad_path = self.dir_path / "from_json.hcad"
        new_hfile = HCADFile.from_json(new_hcad_path, json_path)
        self.assertEqual(new_hfile.row_count, 3)
        self.assertEqual(new_hfile.read_row(2)[0], 300)

    def test_compound_column_csv_interop(self):
        compound_cols = [
            Column(0, 'i'),
            Column(1, '2h'),   # Tuple of 2 shorts
        ]
        rows = [
            [1, (10, 20)],
            [2, (30, 40)],
        ]
        table = Table(compound_cols, rows)
        csv_path = self.dir_path / "compound.csv"
        table.to_csv(csv_path)

        imported = Table.from_csv(csv_path, compound_cols)
        self.assertEqual(imported.rows[0][1], (10, 20))
        self.assertEqual(imported.rows[1][1], (30, 40))

    def test_optional_bridges_missing_dependency_errors(self):
        table = Table(self.cols, self.sample_rows)

        # If pandas not installed, to_pandas and from_pandas raise ImportError
        try:
            import pandas
        except ImportError:
            with self.assertRaises(ImportError) as cm:
                table.to_pandas()
            self.assertIn("pandas is required", str(cm.exception))

            with self.assertRaises(ImportError) as cm:
                Table.from_pandas(None)
            self.assertIn("pandas is required", str(cm.exception))

        # If numpy not installed, to_numpy and from_numpy raise ImportError
        try:
            import numpy
        except ImportError:
            with self.assertRaises(ImportError) as cm:
                table.to_numpy()
            self.assertIn("numpy is required", str(cm.exception))

            with self.assertRaises(ImportError) as cm:
                Table.from_numpy(None, self.cols)
            self.assertIn("numpy is required", str(cm.exception))


if __name__ == '__main__':
    unittest.main()
