#!/usr/bin/env python
import unittest
from uit.test_mutable import TestMutable
from uit.test_utils import TestUtils


class TestMutableCombinations(unittest.TestCase):

    def setUp(self):
        self.device_names = TestUtils.load_config()['device_names']
        if len(self.device_names) < 2:
            raise ValueError(
                "Config must provide at least two devices for combinations.")
        self.device1, self.device2 = self.device_names[:2]
        self.test_mutable = TestMutable()
        self.test_mutable.setUp()

    def tearDown(self):
        self.test_mutable.tearDown()

    def test_combination_of_Detach_Attach(self):
        """
        Test combination: Detach Device2 & Attach Device2
        """
        self.test_mutable.select_application_server()
        self.test_mutable.perform_device_action(
            self.device2, action_type='detach')
        device_detached = self.test_mutable.check_device_in_host_table(
            self.device2, action_type='detach')
        assert device_detached, f"The device '{self.device2}' was still found."
        self.test_mutable.perform_device_action(
            self.device2, action_type='attach')
        device_attached = self.test_mutable.check_device_in_host_table(
            self.device2, action_type='attach')
        assert device_attached, f"The device '{self.device2}' was not found"

    def test_combination_of_Detach_Detach(self):
        """
        Test combination: Detach Device1 & Detach Device2
        """
        self.test_mutable.select_application_server()
        self.test_mutable.perform_device_action(
            self.device2, action_type='detach')
        device_detached = self.test_mutable.check_device_in_host_table(
            self.device2, action_type='detach')
        assert device_detached, f"The device '{self.device2}' was still found."
        self.test_mutable.perform_device_action(
            self.device1, action_type='detach')
        device_detached = self.test_mutable.check_device_in_host_table(
            self.device1, action_type='detach')
        assert device_detached, f"The device '{self.device1}' was still found."

    def test_combination_of_Attach_Detach(self):
        """
        Test combination: Attach Device1 & Detach Device2
        """
        self.test_mutable.select_application_server()
        self.test_mutable.perform_device_action(
            self.device1, action_type='attach')
        device_attached = self.test_mutable.check_device_in_host_table(
            self.device1, action_type='attach')
        assert device_attached, f"The device '{self.device1}' was not found"
        self.test_mutable.perform_device_action(
            self.device1, action_type='detach')
        device_detached = self.test_mutable.check_device_in_host_table(
            self.device1, action_type='detach')
        assert device_detached, f"The device '{self.device1}' was still found."

    def test_combination_of_Attach_Attach(self):
        """
        Test combination: Attach Device1 & Attach Device2
        """
        self.test_mutable.select_application_server()
        self.test_mutable.perform_device_action(
            self.device1, action_type='attach')
        device_attached = self.test_mutable.check_device_in_host_table(
            self.device1, action_type='attach')
        assert device_attached, f"The device '{self.device1}' was not found"
        self.test_mutable.perform_device_action(
            self.device2, action_type='attach')
        device_attached = self.test_mutable.check_device_in_host_table(
            self.device2, action_type='attach')
        assert device_attached, f"The device '{self.device2}' was not found"
