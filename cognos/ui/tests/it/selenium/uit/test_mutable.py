#!/usr/bin/env python
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import unittest
from uit.test_utils import TestUtils


class TestMutable(unittest.TestCase):

    def setUp(self):
        config = TestUtils.load_config()
        self.app_url = config['configure_url']
        self.host_name = config['host_name']
        self.device1 = config['device_names'][0]
        self.device2 = config['device_names'][1]
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
        x = f"//*[@id='app-server-card-id']//td[contains(text(), '{device}')]"
        try:
            if action_type == 'attach':
                WebDriverWait(self.utils.driver, 180, poll_frequency=2).until(
                    EC.visibility_of_element_located((By.XPATH, x)))
            else:
                WebDriverWait(self.utils.driver, 180, poll_frequency=2).until(
                    EC.invisibility_of_element_located((By.XPATH, x)))
            return True
        except Exception:
            return False

    def check_devices_status_in_host_table(self, devices):
        """Return dict of device:T/F based on presence in host table"""
        self.select_application_server()
        status = {}
        for device in devices:
            try:
                x = f"//*[@id='app-server-card-id']//td[contains(text(), "
                f"'{device}')]"
                self.utils.find_element_and_assert(
                    x,
                    By.XPATH,
                    f"Check presence of device '{device}' in host table",
                    self.utils.assert_element_displayed
                )
                status[device] = True
            except AssertionError:
                status[device] = False
        return status

    def perform_device_action(self, device, action_type='attach'):
        """
        Perform attach or detach action for the given device.
        """
        if action_type == 'attach':
            self.utils.click_element_and_assert(
                "[data-testid='attach-id']",
                By.CSS_SELECTOR,
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
                "[data-testid='attach-memory-cancel-button']",
                By.CSS_SELECTOR,
                f"Attach device '{device}'-->click_attach_button",
                self.utils.assert_element_displayed)
        elif action_type == 'detach':
            self.utils.click_element_and_assert(
                "[data-testid='detach-button']",
                By.CSS_SELECTOR,
                f"Detach device '{device}'-->click on remove button",
                self.utils.assert_element_displayed)
            self.utils.click_element_and_assert(
                "[data-testid='cancel-detach-button']",
                By.CSS_SELECTOR,
                f"Detach device '{device}'-->click on detach button",
                self.utils.assert_element_displayed)

    def test_ensure_devices_attached(self):
        """Ensure all given devices are attached. Attach missing ones."""
        devices_status = self.check_devices_status_in_host_table(
                [self.device1, self.device2])
        for device, present in devices_status.items():
            if not present:
                self.perform_device_action(device, action_type='attach')
                device_attached = self.check_device_in_host_table(
                    device, action_type='attach')
                assert device_attached, f"The device '{device}' was not found"

    def test_device_detachment(self):
        """
        Test detachment of CXL devices and check the host table update.
        """
        self.select_application_server()
        self.perform_device_action(self.device2, action_type='detach')
        device_detached = self.check_device_in_host_table(
            self.device2, action_type='detach')
        assert device_detached, f"The device '{self.device2}' was still found."

    def test_CXL_device_attachment(self):
        """
        Test attachment of CXL devices and check the host table update.
        """
        self.select_application_server()
        self.perform_device_action(self.device2, action_type='attach')
        device_attached = self.check_device_in_host_table(
            self.device2, action_type='attach')
        assert device_attached, f"The device '{self.device2}' was not found"
