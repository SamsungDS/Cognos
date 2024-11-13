#!/usr/bin/env python
from uit.test_utils import TestUtils
from selenium.webdriver.common.by import By
import unittest


class TestConfigure(unittest.TestCase):
    def setUp(self):
        self.app_url = TestUtils.load_config()['configure_url']
        self.host_name = TestUtils.load_config()['host_name']
        self.utils = TestUtils(self.app_url)

    def tearDown(self):
        self.utils.tearDown()

    def test_configure_page_displayed(self):
        self.utils.find_element_and_assert(
            "//*[@id='configure-container-id']", By.XPATH,
            "TestCase-HPOS-T81: test_configure_page_displayed",
            self.utils.assert_element_displayed)

    def test_host_table_displayed(self):
        self.utils.find_element_and_assert(
            "//*[@id='app-server-card-id']",
            By.XPATH, "TestCase-HPOS-T38: test_host_table_displayed",
            self.utils.assert_element_displayed)

    def test_memory_box_table_displayed(self):
        self.utils.find_element_and_assert(
            "//*[@id='cmmd-card-id']", By.XPATH,
            "TestCase-HPOS-T44: test_memory_box_table_displayed",
            self.utils.assert_element_displayed)

    def test_memory_box_dropdown(self):
        self.utils.click_element_and_assert(
            "//div[@id='cmmd-card-id']//div[@id='dropdown-container-id']",
            By.XPATH, "TestCase-HPOS-T44: test_memory_box_dropdown",
            self.utils.assert_element_displayed)
        self.utils.click_element_and_assert(
            "//*[@id='react-select-3-option-0']", By.XPATH,
            "TestCase-HPOS-T44: test_memory_box_dropdown",
            self.utils.assert_element_displayed)
