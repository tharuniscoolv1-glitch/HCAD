"""
Tests for legacy procedural functions in src/functions.py.
"""
import tempfile
import unittest
from pathlib import Path

from src.functions import (
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


class TestLegacyFunctions(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_legacy_lifecycle(self):
        filename = "legacy.hcad"
        filepath = str(self.dir_path / filename)
        info = ["i", "f", "H h H"]

        # 1. createNewFile
        createNewFile(filename, str(self.dir_path), info)
        self.assertTrue(validateFile(filepath))

        # 2. getCompressionFromFile & getColumnDescriptions
        self.assertEqual(getCompressionFromFile(filepath), 0)
        col_count, descriptions = getColumnDescriptions(filepath)
        self.assertEqual(col_count, 3)
        self.assertEqual(descriptions, ["i", "f", "H h H"])

        # 3. writeDataToFile
        data = {
            'numberOfColumns': 3,
            'descriptions': ["i", "f", "H h H"],
            'payload': {
                0: [10, 20],
                1: [1.5, 2.5],
                2: [(1, 2, 3), (4, 5, 6)],
            }
        }
        writeDataToFile(filepath, data)

        # 4. readDataFromFile
        result = readDataFromFile(filepath)
        self.assertEqual(result[0], [10, 20])
        self.assertAlmostEqual(result[1][0], 1.5, places=4)
        self.assertEqual(result[2], [(1, 2, 3), (4, 5, 6)])

        # 5. compressDataInFile
        compressDataInFile(filepath)
        self.assertEqual(getCompressionFromFile(filepath), 1)
        self.assertTrue(validateFile(filepath))
        comp_result = readDataFromFile(filepath)
        self.assertEqual(comp_result[0], [10, 20])

        # 6. decompressDataInFile
        decompressDataInFile(filepath)
        self.assertEqual(getCompressionFromFile(filepath), 0)
        self.assertTrue(validateFile(filepath))
        decomp_result = readDataFromFile(filepath)
        self.assertEqual(decomp_result[0], [10, 20])

    def test_make_column_descriptors_bytes_dict_validation(self):
        # Missing key 0 must raise ValueError
        with self.assertRaises(ValueError):
            makeColumnDescriptorsBytes(2, {1: 'i', 2: 'f'}, 32)

        # Extra keys must raise ValueError
        with self.assertRaises(ValueError):
            makeColumnDescriptorsBytes(2, {0: 'i', 1: 'f', 99: 'd'}, 32)


if __name__ == '__main__':
    unittest.main()
