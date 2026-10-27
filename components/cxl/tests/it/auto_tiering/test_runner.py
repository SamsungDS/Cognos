#!/usr/bin/env python
import unittest
import xmlrunner
from tests.start_tuning import StartTuning
from tests.stop_tuning import StopTuning


class TestSuite(unittest.TestCase):

    def run_tests(self):
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(StartTuning)
        suite.addTest(StopTuning(
            "test_stop_tuning"))
        suite.addTest(StopTuning(
            "test_stop_process"))

        runner = xmlrunner.XMLTestRunner(output='svk_tm_reports', verbosity=2)
        result = runner.run(suite)
        if result.wasSuccessful():
            return 0
        else:
            return 1


if __name__ == "__main__":
    exit(TestSuite().run_tests())
