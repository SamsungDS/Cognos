#!/usr/bin/env python
import unittest
import xmlrunner
from uit.test_cognos_pages import CognosPages
from uit.test_dashboard import TestDashboard
from uit.test_configure import TestConfigure


class TestSuite(unittest.TestCase):

    def run_tests(self):
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(CognosPages)
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            TestDashboard))
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            TestConfigure))

        with open("scmc_tests.xml", "wb") as output:
            runner = xmlrunner.XMLTestRunner(output=output, verbosity=2)
            result = runner.run(suite)
        if result.wasSuccessful():
            return 0
        else:
            return 1


if __name__ == "__main__":
    exit(TestSuite().run_tests())
