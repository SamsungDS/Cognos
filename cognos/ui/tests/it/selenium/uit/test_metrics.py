#!/usr/bin/env python
from uit.test_utils import TestUtils
from selenium.webdriver.common.by import By
import unittest


class TestMetrics(unittest.TestCase):

    def setUp(self):
        self.app_url = TestUtils.load_config()['metrics_url']
        self.host_name = TestUtils.load_config()['host_name']
        self.utils = TestUtils(self.app_url)

    def tearDown(self):
        self.utils.tearDown()

    def test_select_application_server(self):
        self.utils.click_element_and_assert(
            "//*[@id='dropdown-container-id']/div/div/div[2]",
            By.XPATH,
            "TestCase-HPOS-T4: select_application_server_dropdown",
            self.utils.assert_element_displayed)

        self.utils.click_element_and_assert(
            f"//div[text()='{self.host_name}']",
            By.XPATH,
            "TestCase-HPOS-T4: Select host from dropdown",
            self.utils.assert_element_displayed)

    def test_Memory_Bandwidth_Display(self):
        self.test_select_application_server()

        self.utils.find_element_and_assert(
            "//*[@id='memory-bandwidth-card-id']", By.XPATH,
            "TestCase-HPOS-T26: test_Memory_Bandwidth_Display",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
            "//*[@id='memory-bandwidth-card-id']/div/div[1]/div",
            By.XPATH,
            "TestCase-HPOS-T26: Progress bar displayed",
            self.utils.assert_element_displayed)

    def test_CPU_vs_Memory_Usage_Graph_Display(self):
        self.test_select_application_server()

        self.utils.find_element_and_assert(
            "//*[@id='saphaana-card-id']", By.XPATH,
            "TestCase-HPOS-T32: test_cpu_vs_memory_usage_graph_display",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
            "//*[@id='saphaana-card-id']//div[@aria-label='A chart.']",
            By.XPATH,
            "TestCase-HPOS-T32: Graph chart component displayed",
            self.utils.assert_element_displayed)

    def test_Memory_Capacity_Piechart_Display(self):
        self.test_select_application_server()

        self.utils.find_element_and_assert(
            "//*[@id='mem-capacity-data-card-id']",
            By.XPATH,
            "TestCase-HPOS-T30: test_Memory_Capacity_Piechart_Display",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
         "//*[@id='mem-capacity-data-card-id']//div[@aria-label='A chart.']",
         By.XPATH,
         "TestCase-HPOS-T30: Pie-Chart component displayed",
         self.utils.assert_element_displayed)

    def test_DRAM_vs_CXL_Memory_Usage_Graph_Display(self):
        self.test_select_application_server()

        self.utils.find_element_and_assert(
            "//*[@id='dram-cxl-mem-data-card-id']", By.XPATH,
            "TestCase-HPOS-T28: test_DRAM_vs_CXL_Memory_Usage_Graph_Display",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
         "//*[@id='dram-cxl-mem-data-card-id']//div[@aria-label='A chart.']",
         By.XPATH,
         "TestCase-HPOS-T28: Graph chart component displayed",
         self.utils.assert_element_displayed)
