#!/usr/bin/env python
from uit.test_utils import TestUtils
from selenium.webdriver.common.by import By
import unittest


class TestMetrics(unittest.TestCase):

    def setUp(self):
        self.app_url = TestUtils.load_config()['metrics_url']
        self.utils = TestUtils(self.app_url)

    def tearDown(self):
        self.utils.tearDown()

    def test_select_application_server(self):
        self.utils.click_element_and_assert(
            "//*[@id='app-server-card-id']", By.XPATH,
            "TestCase-HPOS-T4: test_select_application_server",
            self.utils.assert_element_displayed)

        self.utils.click_element_and_assert(
            "//*[@id='react-select-2-input']", By.XPATH,
            "TestCase-HPOS-T4: Select host from dropdown",
            self.utils.assert_element_displayed)

    def test_memory_bandwidth_display(self):
        self.utils.find_element_and_assert(
            "//*[@id='memory-bandwidth-card-id']", By.XPATH,
            "TestCase-HPOS-T26: test_memory_bandwidth_display",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
            "//*[@id='memory-bandwidth-card-id']/div/div[1]/div", By.XPATH,
            "TestCase-HPOS-T26: test_memory_bandwidth->Progress bar displayed",
            self.utils.assert_element_displayed)

    def test_sap_hana_metrics_display(self):
        self.utils.find_element_and_assert(
            "//*[@id='saphaana-card-id']", By.XPATH,
            "TestCase-HPOS-T32: test_sap_hana_metrics_display",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
            "//*[@id='saphaana-card-id']/div[2]/img", By.XPATH,
            "TestCase-HPOS-T32: test_sap_hana_metrics->live metrics displayed",
            self.utils.assert_element_displayed)

    def test_memory_capacity_piechart_display(self):
        self.utils.find_element_and_assert(
            "//*[@id='mem-capacity-data-card-id']", By.XPATH,
            "TestCase-HPOS-T30: test_memory_capacity_piechart_display",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
            "//*[@id='reactgooglegraph-1']", By.XPATH,
            "TestCase-HPOS-T30: Pie-Chart component displayed",
            self.utils.assert_element_displayed)

    def test_dram_cxl_mem_graph_display(self):
        self.utils.find_element_and_assert(
            "//*[@id='dram-cxl-mem-data-card-id']", By.XPATH,
            "TestCase-HPOS-T28: test_dram_cxl_mem_graph_display",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
            "//*[@id='reactgooglegraph-2']", By.XPATH,
            "TestCase-HPOS-T28: Dram_CXL_Mem Graph chart component displayed",
            self.utils.assert_element_displayed)
