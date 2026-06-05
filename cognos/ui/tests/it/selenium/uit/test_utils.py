#!/usr/bin/env python
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from uit.logger import setup_logger
from selenium.webdriver.common.by import By
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
            username_field = WebDriverWait(self.driver, 120).until(
                EC.presence_of_element_located(
                    (By.ID, "rbac-login-username")))
            username_field.clear()
            username_field.send_keys(username)

            password_field = WebDriverWait(self.driver, 120).until(
                EC.presence_of_element_located(
                    (By.ID, "rbac-login-password")))
            password_field.clear()
            password_field.send_keys(password)

            WebDriverWait(self.driver, 120).until(
                EC.element_to_be_clickable(
                    (By.CLASS_NAME, "rbac-submit-button")))
            # Retry the submit click to survive the first cold-load React
            # hydration race: element_to_be_clickable returns once the button
            # is visible+enabled, but React may not have attached its onClick
            # handler yet, so the first click can be a silent no-op. Re-click
            # only while the submit button is still present (i.e. we are still
            # on the login page); once the sidebar appears, login is done.
            login_succeeded = False
            for attempt in range(6):
                buttons = self.driver.find_elements(
                    By.CLASS_NAME, "rbac-submit-button")
                if not buttons:
                    # Login page has navigated away; assume submit registered.
                    break
                buttons[0].click()
                try:
                    WebDriverWait(self.driver, 20).until(
                        EC.visibility_of_element_located(
                            (By.ID, "side-bar-id")))
                    login_succeeded = True
                    break
                except Exception:
                    self.logger.warning(
                        f"Sidebar not visible after login click "
                        f"(attempt {attempt + 1}); re-checking login state")
            if not login_succeeded:
                WebDriverWait(self.driver, 60).until(
                    EC.visibility_of_element_located((By.ID, "side-bar-id")))
            self.logger.info("Login Successful to SCMC")
        except Exception as e:
            screenshot_path = "/tmp/login_failure.png"
            self.driver.save_screenshot(screenshot_path)
            page_source_path = "/tmp/login_failure.html"
            with open(page_source_path, "w") as f:
                f.write(self.driver.page_source)
            self.logger.error(
                f"Login Failed to SCMC: {str(e)}. "
                f"Screenshot: {screenshot_path}, "
                f"Page source: {page_source_path}")
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
                EC.visibility_of_element_located((locator_type, locator)))
            assert assertion_func(element)
            self.logger.info(f"{test_name} - Passed")
        except Exception as e:
            self.logger.error(f"{test_name} - Failed: {str(e)}")
            raise AssertionError(f"{test_name} - Failed")

    def click_element_and_assert(
            self, locator, locator_type, test_name, assertion_func):
        try:
            element = WebDriverWait(self.driver, 60).until(
                EC.element_to_be_clickable((locator_type, locator)))
            assert assertion_func(element)
            element.click()
            self.logger.info(f"{test_name} - Passed")
        except Exception as e:
            self.logger.error(f"{test_name} - Failed: {str(e)}")
            raise AssertionError(f"{test_name} - Failed")

    def assert_element_displayed(self, element):
        return element.is_displayed()
