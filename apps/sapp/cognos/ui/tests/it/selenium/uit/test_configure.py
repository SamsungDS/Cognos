#!/usr/bin/env python
from uit.test_utils import TestUtils
from selenium.webdriver.common.by import By
import unittest


class TestConfigure(unittest.TestCase):
    def setUp(self):
        config = TestUtils.load_config()
        self.app_url = config['configure_url']
        self.host_name = config['host_name']
        self.utils = TestUtils(self.app_url)
        self.utils.login(config['username'], config['password'])

    def tearDown(self):
        self.utils.tearDown()

    def test_configure_page_displayed(self):
        self.utils.find_element_and_assert(
            "//*[@id='configure-container-id']", By.XPATH,
            "TestCase-HPOS-T81: test_configure_page_displayed",
            self.utils.assert_element_displayed)

    def test_select_application_server(self):
        self.utils.click_element_and_assert(
            "//*[@id='dropdown-container-id']/div/div/div[2]/div",
            By.XPATH,
            "TestCase-HPOS-T38: select_application_server_dropdown",
            self.utils.assert_element_displayed)

        self.utils.click_element_and_assert(
            f"//div[text()='{self.host_name}']", By.XPATH,
            "TestCase-HPOS-T38: Select host from dropdown",
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
            "//*[@id='dropdown-container-id']//*[@role='option'][1]", By.XPATH,
            "TestCase-HPOS-T44: test_memory_box_dropdown",
            self.utils.assert_element_displayed)
