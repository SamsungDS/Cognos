#!/usr/bin/env python
from selenium.webdriver.common.by import By
import unittest
from uit.test_utils import TestUtils


class FrequentPageSwitchTest(unittest.TestCase):

    def setUp(self):
        config = TestUtils.load_config()
        self.app_url = config['scmc_url']
        self.utils = TestUtils(self.app_url)
        self.utils.login(config['username'], config['password'])
        self.pages = [
            {"name": "Dashboard",
             "locator": "//*[@id='side-bar-id']//a[@href='/']",
             "component_xpath": "//*[@id='dashboard-container-id']"},
            {"name": "Metrics Page",
             "locator": "//*[@id='side-bar-id']//a[contains(@href, '/metrics')]",
             "component_xpath": "//*[@id='main-container-id']"},
            {"name": "Device Metrics Page",
             "locator": "//*[@id='side-bar-id']//a[contains(@href, '/device-stats')]",
             "component_xpath": "//*[@id='device-metric-id']"},
            {"name": "Application view page",
             "locator": "//*[@id='side-bar-id']//a[contains(@href, '/application_view')]",
             "component_xpath": "//*[@id='side-bar-id']"},
            {"name": "System alerts page",
             "locator": "//*[@id='side-bar-id']//a[contains(@href, '/events')]",
             "component_xpath": "//*[@id='side-bar-id']"},
            {"name": "About Page",
             "locator": "//*[@id='side-bar-id']//a[contains(@href, '/about')]",
             "component_xpath": "//*[@id='main-container']"},
        ]

    def tearDown(self):
        self.utils.tearDown()

    def test_frequent_page_switching(self):
        for _ in range(3):
            for page in self.pages:
                with self.subTest(page=page["name"]):
                    # Click the page link
                    self.utils.click_element_and_assert(
                        page["locator"], By.XPATH,
                        f"Switch to {page['name']}",
                        self.utils.assert_element_displayed
                    )
                    # Verify the main component of the page is displayed
                    self.utils.find_element_and_assert(
                        page["component_xpath"],
                        By.XPATH,
                        f"{page['name']} component is displayed.",
                        self.utils.assert_element_displayed)
