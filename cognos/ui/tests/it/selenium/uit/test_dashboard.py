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
        self.app_url = TestUtils.load_config()['dashboard_url']
        self.options = Options()
        self.options.add_argument('--headless')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.driver = webdriver.Chrome(options=self.options)
        self.driver.get(self.app_url)
        self.utils = TestUtils(self.app_url)
        self.logger = TestDashboard.logger

    def tearDown(self):
        self.utils.tearDown()

    def test_dashboard_page_displayed(self):
        self.utils.find_element_and_assert(
            "dashboard-container-id", By.ID,
            "test_dashboard_page_displayed",
            self.utils.assert_element_displayed)

    def test_system_topology(self):
        self.utils.find_element_and_assert(
            "topology-card-id", By.ID,
            "TestCase-HPOS-T3: System Toplogy widget displayed",
            self.utils.assert_element_displayed)

    def test_hosts_info_on_hover_in_toplogy(self):
        try:
            host_elements = self.driver.find_elements(
                By.XPATH, "//*[@id='host-card-id']")
            self.assertGreater(len(host_elements), 0)
            for host_element in host_elements:
                assert host_element.is_displayed()
                ActionChains(self.driver).move_to_element(
                    host_element).perform()
                host_tooltip = self.driver.find_element(
                    By.XPATH, "//*[@id='host-card-id']/div[1]/div/span")
                assert host_tooltip.is_displayed()
            self.logger.info(
                "TestCase-HPOS-T57: Hosts info displayed in tooltip - Passed")
            switch_elements = self.driver.find_elements(
                By.XPATH, "//*[@id='cxl-device-card-id']/div[2]")
            self.assertGreater(len(switch_elements), 0)
            for switch_element in switch_elements:
                assert switch_element.is_displayed()
                ActionChains(self.driver).move_to_element(
                    switch_element).perform()
                switch_tooltip = self.driver.find_element(
                    By.XPATH,
                    "//*[@id='cxl-device-card-id']/div[1]/div[1]/div[1]/p")
            assert switch_tooltip.is_displayed()
            self.logger.info(
                "TestCase-HPOS-T57:Displayed hosts info in tooltip - Passed")
        except Exception as e:
            self.logger.error(
                f"TestCase-HPOS-T57:test_hosts_info_on_hover- Failed:{str(e)}")
            self.fail("TestCase-HPOS-T57: test_hosts_info_on_hover - Failed:")

    def test_CMM_D_devices_info_on_hover_in_toplogy(self):
        try:
            device_elements = self.driver.find_elements(
                By.XPATH, "//*[@id='cxl-device-card-id']/div[2]")
            self.assertGreater(len(device_elements), 0)
            for device_element in device_elements:
                assert device_element.is_displayed()
                ActionChains(self.driver).move_to_element(
                    device_element).perform()
                device_tooltip = self.driver.find_element(
                    By.XPATH, "//*[@id='cxl-device-card-id']/div[2]/div[2]")
                device_tooltip.is_displayed()
            self.logger.info(
                "TestCase-HPOS-T58:Displayed CXL devices info - Passed")
        except Exception as e:
            self.logger.error(
                f"TestCase-HPOS-T58:test_CMM_D_devices_info- Failed: {str(e)}")
            self.fail(
                f"TestCase-HPOS-T58:test_CMM_D_devices_info- Failed: {str(e)}")

    def test_system_information(self):
        self.utils.find_element_and_assert(
            "mem-info", By.ID, "TestCase-HPOS-T15: test_system_information",
            self.utils.assert_element_displayed)

    def test_system_memory_allocated(self):
        self.utils.find_element_and_assert(
            "sys-mem-allocated-id", By.ID,
            "TestCase-HPOS-T16: test_system_memory_allocated",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
            "//*[@id='sys-mem-allocated-id']/div[2]/div[2]/div[1]/div",
            By.XPATH,
            "TestCase-HPOS-T16: test_system_memory-->Progress bars displayed",
            self.utils.assert_element_displayed)

    def test_system_health_status(self):
        self.utils.find_element_and_assert(
            "health-container-id", By.ID,
            "TestCase-HPOS-T17: test_system_health_status",
            self.utils.assert_element_displayed)

    def test_system_bandwidth_graph(self):
        self.utils.find_element_and_assert(
            "rack-graph-id", By.ID,
            "TestCase-HPOS-T18: test_system_bandwidth_graph",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
            "//h6[contains(text(), 'System Bandwidth')]", By.XPATH,
            "TestCase-HPOS-T18: System Bandwidth Text displayed",
            self.utils.assert_element_displayed)

    def test_cmmd_graph(self):
        self.utils.find_element_and_assert(
            "cmm-graph-id", By.ID, "TestCase-HPOS-T21: test_cmmd_graph",
            self.utils.assert_element_displayed)

        self.utils.find_element_and_assert(
            "//h6[contains(text(), 'CMM-D')][@style='font-weight: bold;']",
            By.XPATH,
            "TestCase-HPOS-T21: test_cmmd_graph-->CMM-D Text displayed",
            self.utils.assert_element_displayed)
