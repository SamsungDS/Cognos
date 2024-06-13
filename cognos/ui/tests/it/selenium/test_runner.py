#!/usr/bin/env python
import unittest
from uit.test_cognos_pages import CognosPages
from uit.test_dashboard import TestDashboard
from uit.test_metrics import TestMetrics
from uit.test_configure import TestConfigure


class TestSuite(unittest.TestCase):

    def run_tests(self):
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(CognosPages)
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            TestDashboard))
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            TestConfigure))
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            TestMetrics))
        runner = unittest.TextTestRunner(verbosity=2)
        runner.run(suite)


if __name__ == "__main__":
    TestSuite().run_tests()
