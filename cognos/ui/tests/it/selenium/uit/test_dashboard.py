#!/usr/bin/env python
from selenium import webdriver
from selenium.webdriver.common.by import By
from uit.logger import setup_logger
from selenium.webdriver.common.action_chains import ActionChains
import unittest
from selenium.webdriver.chrome.options import Options
from uit.test_utils import TestUtils


class TestDashboard(unittest.TestCase):
    logger = setup_logger()

    def setUp(self):
        config = TestUtils.load_config()
        self.app_url = config['dashboard_url']
        self.utils = TestUtils(self.app_url)
        self.utils.login(config['username'], config['password'])
        self.logger = TestDashboard.logger

    def tearDown(self):
        self.utils.tearDown()

    def test_dashboard_page_displayed(self):
        self.utils.find_element_and_assert(
            "dashboard-container-id",
            By.ID,
            "TestCase-HPOS-T82: test_dashboard_page_displayed",
            self.utils.assert_element_displayed)

    def test_system_topology(self):
        self.utils.find_element_and_assert(
            "topology-card-id",
            By.ID,
            "TestCase-HPOS-T3: System Toplogy widget displayed",
            self.utils.assert_element_displayed)

    def test_hosts_info_on_hover_in_toplogy(self):
        try:
            host_elements = self.utils.driver.find_elements(
                By.XPATH, "//*[@id='host-card-id']/div/div")
            self.assertGreater(len(host_elements), 0)
            host_tooltip = self.utils.driver.find_element(
                By.XPATH, "//*[@id='host-card-id']/div[2]/div/span")
            ActionChains(self.utils.driver).move_to_element(
                    host_tooltip).perform()
            assert host_tooltip.is_displayed()
            self.logger.info(
                "TestCase-HPOS-T57:Displayed hosts info in tooltip - Passed")
        except Exception as e:
            self.logger.error(
                f"TestCase-HPOS-T57:test_hosts_info_on_hover- Failed:{str(e)}")
            self.fail("TestCase-HPOS-T57: test_hosts_info_on_hover - Failed:")

    def test_tooltip_display_CMM_D_devices_info_on_hover_in_toplogy(self):
        try:
            device_elements = self.utils.driver.find_elements(
                By.XPATH, "//*[@id='cxl-device-card-id']/div/div")
            self.assertGreater(len(device_elements), 0)
            device_tooltip = self.utils.driver.find_element(
                    By.XPATH, "//*[@id='cxl-device-card-id']/div/div[3]")
            ActionChains(self.utils.driver).move_to_element(
                    device_tooltip).perform()
            device_tooltip.is_displayed()
            self.logger.info(
                "TestCase-HPOS-T58:Displayed devices info in tooltip - Passed")
        except Exception as e:
            self.logger.error(
                f"TestCase-HPOS-T58:test_CMM_D_devices_info- Failed: {str(e)}")
            self.fail(
                f"TestCase-HPOS-T58:test_CMM_D_devices_info- Failed: {str(e)}")

    def test_CMM_B_boxes_selection_in_toplogy(self):
        try:
            cmm_b_boxes = self.utils.driver.find_elements(
                By.XPATH, "//*[@id='topology-card-id']/div/div/div[1]/span")
            self.assertGreater(len(cmm_b_boxes), 0)
            for cmm_b_box in cmm_b_boxes:
                assert cmm_b_box.is_displayed()
                ActionChains(self.utils.driver).click(cmm_b_box).perform()
            self.logger.info(
                    "TestCase-HPOS-T123 :CMM_B_boxes selection - Passed")
        except Exception as e:
            self.logger.error(
             f"TestCase-HPOS-T123:test_CMM_B_boxes_selection-Failed: {str(e)}")
            self.fail(
             f"TestCase-HPOS-T123:test_CMM_B_boxes_selection-Failed: {str(e)}")

    def test_selecting_next_arrow_in_toplogy(self):
        self.utils.find_element_and_assert(
            "//*[@id='topology-card-id']/div/div/div[1]/button[2]",
            By.XPATH,
            "TestCase-HPOS-Ti121 : Clicking next arrow in toplogy",
            self.utils.assert_element_displayed)

    def test_selecting_previous_arrow_in_toplogy(self):
        self.utils.find_element_and_assert(
            "//*[@id='topology-card-id']/div/div/div[1]/button[1]",
            By.XPATH,
            "TestCase-HPOS-T120: Clicking previous arrow in toplogy",
            self.utils.assert_element_displayed)

    def test_system_information(self):
        self.utils.find_element_and_assert(
            "mem-info", By.ID, "TestCase-HPOS-T15: test_system_information",
            self.utils.assert_element_displayed)

    def test_CMM_B_memory_bandwidth(self):
        self.utils.find_element_and_assert(
            "sys-mem-allocated-id", By.ID,
            "TestCase-HPOS-T16: test_CMM-B_memory_bandwidth",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
            "//*[@id='sys-mem-allocated-id']/div[2]/div/div[2]",
            By.XPATH,
            "TestCase-HPOS-T16: CMM-B Memory Bandwith Progress bar displayed",
            self.utils.assert_element_displayed)

    def test_CMM_B_memory_capacity(self):
        self.utils.find_element_and_assert(
            "sys-mem-allocated-id", By.ID,
            "TestCase-HPOS-T18: test_CMM-B_memory_capacity",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
            "//*[@id='sys-mem-allocated-id']/div[2]/div/div[2]",
            By.XPATH,
            "TestCase-HPOS-T18: CMM-B Memory Capacity Progress bar displayed",
            self.utils.assert_element_displayed)

    def test_CMM_B_memory_usage_graph(self):

        self.utils.find_element_and_assert(
            "rack-graph-id",
            By.ID,
            "TestCase-HPOS-T21: test_cmm-b_memory_usage_graph",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
         "//h6[contains(text(), 'CMM-B Memory')]",
         By.XPATH,
         "TestCase-HPOS-T21: CMM-B Memory Usage Text displayed",
         self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
         "//div[@data-testid='rackBandwidth-id']//div[@aria-label='A chart.']",
         By.XPATH,
         "TestCase-HPOS-T21: Graph component displayed",
         self.utils.assert_element_displayed)
