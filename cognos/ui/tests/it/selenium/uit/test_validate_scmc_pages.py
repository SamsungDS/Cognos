#!/usr/bin/env python
from selenium.webdriver.common.by import By
import unittest
from uit.test_utils import TestUtils


class PageValidationTest(unittest.TestCase):

    def setUp(self):
        config = TestUtils.load_config()
        self.app_url = config['scmc_url']
        self.utils = TestUtils(self.app_url)
        self.utils.login(config['username'], config['password'])
        # Define pages with locators and expected widgets
        self.pages = [
            {
                "name": "Dashboard",
                "locator": "//div[@id='side-bar-id']/div/a[1]",
                "widgets": [
                    {"name": "memory-box-overview",
                     "xpath": "//*[@id='memory-box-overview-id']"},
                    {"name": "topology",
                     "xpath": "//*[@id='topology-card-id']"},
                    {"name": "mem-info",
                     "xpath": "//*[@id='mem-info']"},
                    {"name": "sys-mem-allocated",
                     "xpath": "//*[@id='sys-mem-allocated-id']"},
                    {"name": "CMMB-memory-usage-graph",
                     "xpath": "//*[@id='rack-graph-id']"},
                    {"name": "CMMB-memory-bandwidth",
                     "xpath": ("//*[@id='dashboard-container-id']/div/"
                               "div[3]/div[2]")},
                ],
            },
            {
                "name": "Configure Page",
                "locator": "//*[@id='side-bar-id']/div/a[2]",
                "widgets": [
                    {"name": "Host Table",
                     "xpath": "//*[@id='app-server-card-id']"},
                    {"name": "CMMB Table",
                     "xpath": "//*[@id='cmmd-card-id']"},
                ],
            },
            {
                "name": "Metrics Page",
                "locator": "//*[@id='side-bar-id']/div/a[3]",
                "widgets": [
                    {"name": "Host Selectot",
                     "xpath": "//*[@id='app-server-card-id']"},
                    {"name": "Host Bandwidth",
                     "xpath": "//*[@id='memory-bandwidth-card-id']"},
                    {"name": "CPU vs Memory Usage Graph",
                     "xpath": "//*[@id='saphaana-card-id']"},
                    {"name": "Memory Capacity",
                     "xpath": "//*[@id='mem-capacity-data-card-id']"},
                    {"name": "CPU vs Memory Usage Graph",
                     "xpath": "//*[@id='dram-cxl-mem-data-card-id']"},
                ],
            },
            {
                "name": "About Page",
                "locator": "//*[@id='side-bar-id']/div/a[6]",
                "widgets": [
                    {"name": "About widget1",
                     "xpath": ("//*[@id='main-container']/div/div[1]/"
                               "div[1]")},
                    {"name": "About widget2",
                     "xpath": "//*[@id='mem-box-imgae']"},
                    {"name": "About widget3",
                     "xpath": "//*[@id='description-1']"},
                    {"name": "About widget4",
                     "xpath": "//*[@id='description-2']"},
                    {"name": "About widget5",
                     "xpath": "//*[@id='description-3']"},
                ],
            },
        ]

    def tearDown(self):
        self.utils.tearDown()

    def test_validate_widgets(self):
        """Validate all widgets on the page."""
        for page in self.pages:
            with self.subTest(page=page["name"]):
                self.utils.click_element_and_assert(
                    page["locator"], By.XPATH,
                    f"Navigate to {page['name']}",
                    self.utils.assert_element_displayed,
                )
                print(f"Validating widgets for {page['name']}...")
                for widget in page["widgets"]:
                    with self.subTest(widget=widget["name"]):
                        try:
                            element = self.utils.driver.find_element(
                                    By.XPATH, widget["xpath"])
                            is_displayed = self.utils.assert_element_displayed(
                                element
                            )
                            if is_displayed:
                                self.utils.logger.info(
                                    f"Widget '{widget['name']}' is displayed "
                                    f"on {page['name']}."
                                )
                            else:
                                self.utils.logger.warning(
                                    f"Widget '{widget['name']}' is NOT "
                                    f"displayed on {page['name']}."
                                )
                            self.assertTrue(
                                is_displayed,
                                f"Widget {widget['name']} is not displayed on "
                                f"{page['name']}",
                            )
                            duplicate_check_xpath = f"{widget['xpath']}[2]"
                            duplicate_elements = (
                                self.utils.driver.find_elements(
                                    By.XPATH, duplicate_check_xpath
                                )
                            )
                            if duplicate_elements:
                                self.utils.logger.error(
                                    f"Duplicate widget '{widget['name']}' "
                                    f"found on {page['name']}."
                                )
                            else:
                                self.utils.logger.info(
                                    f"No duplicate widget '{widget['name']}' "
                                    f"found on {page['name']}."
                                )
                            self.assertFalse(
                                duplicate_elements,
                                f"Duplicate widget {widget['name']} found on "
                                f"{page['name']}",
                            )
                        except Exception as e:
                            self.utils.logger.error(
                                f"Error validating widget '{widget['name']}' "
                                f"on {page['name']}: {str(e)}"
                            )
                            raise

    def test_ui_break_checks(self):
        for page in self.pages:
            with self.subTest(page=page["name"]):
                self.utils.click_element_and_assert(
                    page["locator"], By.XPATH,
                    f"Navigate to {page['name']}",
                    self.utils.assert_element_displayed,
                )
                self.check_ui_consistency(page["name"])

    def check_ui_consistency(self, page_name):
        """Check for common UI break issues with logging."""
        try:
            logs = self.utils.driver.get_log("browser")
            js_error_found = False
            for log in logs:
                if "error" in log["message"].lower():
                    self.utils.logger.error(
                        f"JavaScript error on {page_name}: {log['message']}"
                    )
                    js_error_found = True
            if not js_error_found:
                self.utils.logger.info(
                    f"No JavaScript errors found on {page_name}."
                )
            images = self.utils.driver.find_elements(By.TAG_NAME, "img")
            broken_images = []
            for img in images:
                if img.get_attribute("naturalWidth") == "0":
                    src = img.get_attribute("src")
                    broken_images.append(src)
                    self.utils.logger.error(
                        f"Broken image found on {page_name}: {src}"
                    )
            if broken_images:
                self.fail(
                    f"Broken images found on {page_name}: {broken_images}"
                )
            else:
                self.utils.logger.info(
                    f"No broken images found on {page_name}."
                )
        except Exception as e:
            self.utils.logger.error(
                f"UI consistency check failed on {page_name}: {str(e)}"
            )
            raise
