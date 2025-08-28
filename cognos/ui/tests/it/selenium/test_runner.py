#!/usr/bin/env python
import unittest
import xmlrunner
from uit.test_cognos_pages import CognosPages
from uit.test_dashboard import TestDashboard
from uit.test_configure import TestConfigure
from uit.test_metrics import TestMetrics
from uit.test_mutable import TestMutable
from uit.test_mutable_combinations import TestMutableCombinations
from uit.test_frequent_switch_pages import FrequentPageSwitchTest
from uit.test_validate_scmc_pages import PageValidationTest
from uit.test_frequent_select_devices import TestSelectDevices


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
        suite.addTest(TestMutable(
            "test_device_detachment"))
        suite.addTest(TestMutable(
            "test_CXL_device_attachment"))
        suite.addTest(TestMutableCombinations(
            "test_combination_of_Detach_Attach"))
        suite.addTest(TestMutableCombinations(
            "test_combination_of_Detach_Detach"))
        suite.addTest(TestMutableCombinations(
            "test_combination_of_Attach_Detach"))
        suite.addTest(TestMutableCombinations(
            "test_combination_of_Attach_Attach"))
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            FrequentPageSwitchTest))
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            PageValidationTest))
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            TestSelectDevices))
        with open("scmc_tests.xml", "wb") as output:
            runner = xmlrunner.XMLTestRunner(output=output, verbosity=2)
            result = runner.run(suite)
        if result.wasSuccessful():
            return 0
        else:
            return 1


if __name__ == "__main__":
    exit(TestSuite().run_tests())
