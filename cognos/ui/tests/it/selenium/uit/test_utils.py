#!/usr/bin/env python
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from uit.logger import setup_logger
from selenium.webdriver.common.by import By
import time
import os
import json


class TestUtils:

    logger = setup_logger()

    def __init__(self, url):
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.set_capability("acceptInsecureCerts", True)
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--ignore-ssl-errors=yes')
        options.add_argument('--allow-insecure-localhost')
        self.driver = webdriver.Chrome(options=options)
        self.driver.get(url)

    def login(self, username, password):
        try:
            username_field = WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located(
                    (By.ID, "rbac-login-username")))
            username_field.clear()
            username_field.send_keys(username)

            password_field = WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located(
                    (By.ID, "rbac-login-password")))
            password_field.clear()
            password_field.send_keys(password)

            login_button = WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, "rbac-submit-button")))
            login_button.click()
            time.sleep(2)
            self.logger.info("Login Successful to SCMC")
        except Exception as e:
            self.logger.error(f"Login Failed to SCMC: {str(e)}")
            raise AssertionError("Login Failed")

    def tearDown(self):
        self.driver.quit()

    def load_config():
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, '..', 'config', 'config.json')
        with open(config_path) as config_file:
            config = json.load(config_file)
            return config

    def find_element_and_assert(
            self, locator, locator_type, test_name, assertion_func):
        try:
            element = WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located((locator_type, locator)))
            assert assertion_func(element)
            self.logger.info(f"{test_name} - Passed")
        except Exception as e:
            self.logger.error(f"{test_name} - Failed: {str(e)}")
            raise AssertionError(f"{test_name} - Failed")

    def click_element_and_assert(
            self, locator, locator_type, test_name, assertion_func):
        try:
            element = WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located((locator_type, locator)))
            assert assertion_func(element)
            element.click()
            time.sleep(5)
            self.logger.info(f"{test_name} - Passed")
        except Exception as e:
            self.logger.error(f"{test_name} - Failed: {str(e)}")
            raise AssertionError(f"{test_name} - Failed")

    def assert_element_displayed(self, element):
        return element.is_displayed()
