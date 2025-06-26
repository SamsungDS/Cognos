#!/usr/bin/env python
from selenium.webdriver.common.by import By
import unittest
from uit.test_utils import TestUtils


class FrequentPageSwitchTest(unittest.TestCase):
    def setUp(self):
        self.app_url = TestUtils.load_config()['scmc_url']
        self.utils = TestUtils(self.app_url)
        self.pages = [
            {"name": "Dashboard",
             "locator": "//div[@id='side-bar-id']/div/a[1]",
             "component_xpath": "//*[@id='dashboard-container-id']"},
            {"name": "Configure Page",
             "locator": "//*[@id='side-bar-id']/div/a[2]",
             "component_xpath": "//*[@id='configure-container-id']"},
            {"name": "Metrics Page",
             "locator": "//*[@id='side-bar-id']/div/a[3]",
             "component_xpath": "//*[@id='main-container-id']"},
            {"name": "About Page",
             "locator": "//*[@id='side-bar-id']/div/a[5]",
             "component_xpath": "//*[@id='main-container']"},
        ]

    def tearDown(self):
        self.utils.tearDown()

    def test_frequent_page_switching(self):
        for _ in range(10):
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
