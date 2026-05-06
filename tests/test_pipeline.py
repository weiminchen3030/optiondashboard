import unittest

from options_signal_pipeline.pipeline import filter_contracts, detect_clustering


class PipelineTestCase(unittest.TestCase):
    def test_filter_contracts_empty(self):
        result = filter_contracts(None)
        self.assertEqual(result.shape[0], 0)

    def test_detect_clustering_empty(self):
        result = detect_clustering(None)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
