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

    def test_configure_page_click(self):
        self.utils.click_element_and_assert(
            "//*[@id='side-bar-id']/div/a[2]", By.XPATH,
            "TestCase-HPOS-T34: test_configure_page_click",
            self.utils.assert_element_displayed)

    def test_metrics_page_click(self):
        self.utils.click_element_and_assert(
            "//*[@id='side-bar-id']/div/a[3]", By.XPATH,
            "TestCase-HPOS-T25: test_metrics_page_click",
            self.utils.assert_element_displayed)

    def test_about_page_click(self):
        self.utils.click_element_and_assert(
            "//*[@id='side-bar-id']/div/a[7]", By.XPATH,
            "TestCase-HPOS-T49: test_about_page_click",
            self.utils.assert_element_displayed)
