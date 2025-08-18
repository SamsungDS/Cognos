#!/usr/bin/env python
from selenium.webdriver.common.by import By
import unittest
from uit.test_utils import TestUtils
import time


class TestMutable(unittest.TestCase):

    def setUp(self):
        config = TestUtils.load_config()
        self.app_url = config['configure_url']
        self.host_name = config['host_name']
        self.device = config['device_names'][1]
        self.utils = TestUtils(self.app_url)
        self.utils.login(config['username'], config['password'])

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

    def check_device_in_host_table(self, device, action_type='attach'):
        max_wait_time = 180
        check_interval = 30
        start_time = time.time()
        x = f"//*[@id='app-server-card-id']//td[contains(text(), '{device}')]"
        while time.time() - start_time < max_wait_time:
            try:
                self.utils.find_element_and_assert(
                    x,
                    By.XPATH,
                    f"Check presence of device '{device}' in host table",
                    self.utils.assert_element_displayed
                )
                if action_type == 'attach':
                    return True
            except AssertionError:
                if action_type == 'detach':
                    return True
            time.sleep(check_interval)

        return False

    def perform_device_action(self, device, action_type='attach'):
        """
        Perform attach or detach action for the given device.
        """
        if action_type == 'attach':
            self.utils.click_element_and_assert(
                "//*[@id='app-server-card-id']//tr[last()]/td/button",
                By.XPATH,
                f"Attach device '{device}'-->click on add button",
                self.utils.assert_element_displayed)
            self.utils.click_element_and_assert(
                f"//*[@id='logicalMemoryDevice']/option[@value='{device}']",
                By.XPATH,
                f"Attach device '{device}'-->select_device",
                self.utils.assert_element_displayed)
            self.utils.click_element_and_assert(
                "//*[@id='memoryMode']/option",
                By.XPATH,
                f"Attach device '{device}'-->select_memory_mode",
                self.utils.assert_element_displayed)
            self.utils.click_element_and_assert(
                "//*[@id='attach-modal-id']/div/div[3]/button[3]",
                By.XPATH,
                f"Attach device '{device}'-->click_attach_button",
                self.utils.assert_element_displayed)
        elif action_type == 'detach':
            self.utils.click_element_and_assert(
                "//*[@id='app-server-card-id']//tr[last()-1]/td/button",
                By.XPATH, f"Detach device '{device}'-->click on remove button",
                self.utils.assert_element_displayed)
            self.utils.click_element_and_assert(
                "//*[@id='detach-mem-modal-id']/div/div[3]/button[2]",
                By.XPATH,
                f"Detach device '{device}'-->click on detach button",
                self.utils.assert_element_displayed)

    def test_device_detachment(self):
        """
        Test detachment of CXL devices and check the host table update.
        """
        self.select_application_server()
        self.perform_device_action(self.device, action_type='detach')
        device_detached = self.check_device_in_host_table(
            self.device, action_type='detach')
        assert device_detached, f"The device '{self.device}' was still found."

    def test_CXL_device_attachment(self):
        """
        Test attachment of CXL devices and check the host table update.
        """
        self.select_application_server()
        self.perform_device_action(self.device, action_type='attach')
        device_attached = self.check_device_in_host_table(
            self.device, action_type='attach')
        assert device_attached, f"The device '{self.device}' was not found"
