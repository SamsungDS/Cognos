import unittest
from uit.test_utils import TestUtils
from selenium.webdriver.common.by import By


class TestSelectDevices(unittest.TestCase):

    def setUp(self):
        self.app_url = TestUtils.load_config()['configure_url']
        self.host_name = TestUtils.load_config()['host_name']
        self.utils = TestUtils(self.app_url)

    def tearDown(self):
        self.utils.tearDown()

    def select_application_server(self):
        self.utils.click_element_and_assert(
         "//*[@id='dropdown-container-id']/div/div/div[2]/div",
         By.XPATH,
         "TestCase-HPOS-T38: select_application_server_dropdown",
         self.utils.assert_element_displayed)
        self.utils.click_element_and_assert(
            f"//div[text()='{self.host_name}']",
            By.XPATH,
            "TestCase-HPOS-T38: Select host from dropdown",
            self.utils.assert_element_displayed)

    def test_select_all_devices_frequently(self):
        iterations = 10
        self.select_application_server()
        for i in range(iterations):
            print(f"Iteration {i+1}/{iterations}...")
            self.utils.click_element_and_assert(
                    "//*[@id='app-server-card-id']//tr[last()]/td/button",
                    By.XPATH,
                    "click on add button",
                    self.utils.assert_element_displayed
                )
            device_options_xpath = "//*[@id='logicalMemoryDevice']/option"
            device_options = self.utils.driver.find_elements(
                By.XPATH, device_options_xpath)
            if not device_options:
                print("No devices available in the dropdown.")
                break
            for device_option in device_options:
                dev = device_option.get_attribute("value")
                if dev == "Select CXL Device" or not dev:
                    continue
                self.utils.click_element_and_assert(
                    f"//*[@id='logicalMemoryDevice']/option[@value='{dev}']",
                    By.XPATH,
                    f"Select CXL Device --> '{dev}'",
                    self.utils.assert_element_displayed
                )
            self.utils.click_element_and_assert(
                "//*[@id='attach-modal-id']/div/div[3]/button[2]",
                By.XPATH,
                "Click on Cancel button",
                self.utils.assert_element_displayed
            )
        print(f"Completed iteration {i+1}/{iterations}.")
