#!/usr/bin/env python
from selenium.webdriver.common.by import By
import unittest
from uit.test_utils import TestUtils


class CognosPages(unittest.TestCase):

    def setUp(self):
        config = TestUtils.load_config()
        self.app_url = config['scmc_url']
        self.utils = TestUtils(self.app_url)
        self.utils.login(config['username'], config['password'])

    def tearDown(self):
        self.utils.tearDown()

    def test_application_launched_to_dashboard(self):
        self.utils.click_element_and_assert(
            "//div[@id='side-bar-id']", By.XPATH,
            "TestCase-HPOS-T82: test_application_launched_to_dashboard",
            self.utils.assert_element_displayed)

    def test_metrics_page_click(self):
        self.utils.click_element_and_assert(
            "//*[@id='side-bar-id']//a[contains(@href, '/metrics')]", By.XPATH,
            "TestCase-HPOS-T34: test_metrics_page_click",
            self.utils.assert_element_displayed)

    def test_device_metrics_page_click(self):
        self.utils.click_element_and_assert(
            "//*[@id='side-bar-id']//a[contains(@href, '/device-stats')]",
            By.XPATH,
            "TestCase-HPOS-T25: test_device_metrics_page_click",
            self.utils.assert_element_displayed)

    def test_application_view_page_click(self):
        self.utils.click_element_and_assert(
            "//*[@id='side-bar-id']//a[contains(@href, '/application_view')]",
            By.XPATH,
            "TestCase-HPOS-T25: test_application_view_page_click",
            self.utils.assert_element_displayed)

    def test_systemc_alerts_page_click(self):
        self.utils.click_element_and_assert(
            "//*[@id='side-bar-id']//a[contains(@href, '/events')]", By.XPATH,
            "TestCase-HPOS-T25: test_system_alerts_page_click",
            self.utils.assert_element_displayed)

    def test_about_page_click(self):
        self.utils.click_element_and_assert(
            "//*[@id='side-bar-id']//a[contains(@href, '/about')]", By.XPATH,
            "TestCase-HPOS-T49: test_about_page_click",
            self.utils.assert_element_displayed)
