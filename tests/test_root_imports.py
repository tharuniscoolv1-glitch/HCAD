"""
Tests verifying that all procedural functions and classes can be imported
directly from the top-level `hcad` package.
"""
import tempfile
import unittest
from pathlib import Path

# Direct imports from hcad
import hcad
from hcad import (
    createNewFile,
    validateFile,
    writeDataToFile,
    readDataFromFile,
    getCompressionFromFile,
    getColumnDescriptions,
    compressDataInFile,
    decompressDataInFile,
    HCADFile,
    Table,
    Column,
)


class TestRootImports(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_version_string(self):
        self.assertEqual(hcad.__version__, "0.1.1")

    def test_direct_function_call(self):
        filename = "root_test.hcad"
        filepath = str(self.dir_path / filename)

        # 1. createNewFile directly imported from hcad
        createNewFile(filename, str(self.dir_path), ["i", "f"])
        self.assertTrue(validateFile(filepath))

        # 2. writeDataToFile directly imported
        data = {
            'numberOfColumns': 2,
            'descriptions': ["i", "f"],
            'payload': {
                0: [100],
                1: [3.14],
            }
        }
        writeDataToFile(filepath, data)

        # 3. readDataFromFile directly imported
        result = readDataFromFile(filepath)
        self.assertEqual(result[0], [100])
        self.assertAlmostEqual(result[1][0], 3.14, places=2)

    def test_module_level_attribute_access(self):
        # Access via hcad.<function>
        self.assertTrue(callable(hcad.createNewFile))
        self.assertTrue(callable(hcad.writeDataToFile))
        self.assertTrue(callable(hcad.readDataFromFile))
        self.assertTrue(callable(hcad.validateFile))
        self.assertTrue(callable(hcad.compressDataInFile))
        self.assertTrue(callable(hcad.decompressDataInFile))


if __name__ == '__main__':
    unittest.main()
