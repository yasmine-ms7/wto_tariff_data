import re
import time
import logging
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
# =============================
# DRIVER
# =============================


def start_driver(timeout: int = 30):
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = uc.Chrome(options=options, version_main=145)

    wait = WebDriverWait(driver, timeout)
    return driver, wait


# =============================
# CHOICES.JS HELPERS
# =============================


def select_choice(wait: WebDriverWait, select_id: str, visible_text: str):
    """
    select_id: id of hidden <select> (reporters, years, indicator)
    visible_text: exact visible option text
    """
    container = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                f"//select[@id='{select_id}']/ancestor::div[contains(@class,'choices')]",
            )
        )
    )
    container.click()

    option = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                f"//div[contains(@class,'choices__item') and text()='{visible_text}']",
            )
        )
    )
    option.click()

    # Replace sleep with "value actually applied" wait:
    # we wait until the selected item chip appears in the choices container.
    wait.until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                f"//select[@id='{select_id}']/ancestor::div[contains(@class,'choices')]"
                f"//div[contains(@class,'choices__item--selectable') or contains(@class,'choices__item--selected')][contains(.,\"{visible_text}\")]",
            )
        )
    )


def apply_filters(driver, wait: WebDriverWait):
    select_choice(wait, "reporters", "Albania")
    select_choice(wait, "years", "Latest available year")
    select_choice(wait, "indicator", "MFN applied duty")

    apply_button = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(.,'Apply filter') and not(@disabled)]")
        )
    )
    apply_button.click()

    # Wait for table
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
    logging.info("Filtering completed successfully.")


# =============================
# DOWNLOAD MODAL
# =============================


def open_download_modal(driver, wait: WebDriverWait):
    download_button = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Download data')]"))
    )
    driver.execute_script("arguments[0].click();", download_button)
    logging.info("Download button clicked.")

    wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[contains(@class,'fixed') or contains(@class,'modal')]")
        )
    )
    logging.info("Download popup appeared.")


def fill_email(wait: WebDriverWait, email: str):
    email_input = wait.until(
        EC.element_to_be_clickable((By.ID, "mountedActionsData.0.email"))
    )
    email_input.clear()
    email_input.send_keys(email)
    logging.info("Email filled successfully.")


def switch_into_iframe_if_present(driver):
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    if iframes:
        logging.info("Iframe detected. Switching into iframe.")
        driver.switch_to.frame(iframes[-1])
    else:
        logging.info("No iframe detected.")


# =============================
# CAPTCHA
# =============================


def _solve_captcha_text(captcha_text: str) -> int:
    # Clean text like "4 + 9 = ?"
    cleaned = captcha_text.replace("=", "").replace("?", "").strip()

    match = re.search(r"(\d+)\s*([\+\-\*])\s*(\d+)", cleaned)
    if not match:
        raise Exception(f"Could not parse captcha: {captcha_text}")

    num1 = int(match.group(1))
    op = match.group(2)
    num2 = int(match.group(3))

    if op == "+":
        return num1 + num2
    if op == "-":
        return num1 - num2
    if op == "*":
        return num1 * num2

    raise Exception(f"Unknown operator in captcha: {captcha_text}")


def fill_captcha(driver, wait: WebDriverWait):
    logging.info("Waiting for captcha...")

    # Wait until at least one captcha element exists
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.bg-green-100")))

    # Livewire duplicates: take the LAST visible one
    captcha_boxes = driver.find_elements(By.CSS_SELECTOR, "div.bg-green-100")
    if not captcha_boxes:
        raise Exception("No captcha elements found.")

    captcha_box = captcha_boxes[-1]

    # Wait until it actually contains text
    wait.until(lambda d: captcha_box.text.strip() != "")

    captcha_text = captcha_box.text.strip()
    logging.info("Captcha raw text:", captcha_text)

    result = _solve_captcha_text(captcha_text)
    logging.info("Captcha solved:", result)

    captcha_input = wait.until(
        EC.element_to_be_clickable((By.ID, "mountedActionsData.0.captcha"))
    )
    captcha_input.clear()
    captcha_input.send_keys(str(result))
    logging.info("Captcha filled.")


# =============================
# TERMS CHECKBOX
# =============================


def ensure_terms_checked(driver, wait: WebDriverWait):
    terms_checkbox = wait.until(
        EC.presence_of_element_located((By.ID, "mountedActionsData.0.terms"))
    )

    if not terms_checkbox.is_selected():
        driver.execute_script("arguments[0].click();", terms_checkbox)

    # Confirm
    if not terms_checkbox.is_selected():
        raise Exception("Terms checkbox could not be checked.")

    logging.info("Terms checkbox confirmed checked.")


# =============================
# SUBMIT + VERIFY SUCCESS
# =============================


def click_visible_submit_and_wait_success(driver, wait: WebDriverWait):
    submit_button = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//div[contains(@class,'fi-modal-footer-actions')]//button[@type='submit' and not(@disabled)]",
            )
        )
    )

    # This tiny pause is the only one I keep (Livewire/Alpine repaint after scroll).
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});", submit_button
    )
    # If you REALLY want 0 sleeps, remove it and increase waits below;
    # but in practice this 0.2-0.5s helps stability a lot.

    time.sleep(0.5)

    driver.execute_script("arguments[0].click();", submit_button)
    logging.info("VISIBLE submit clicked.")

    # Wait for toast
    wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//*[contains(text(),'Email submitted')]")
        )
    )
    logging.info("Success popup detected.")


# =============================
# MAIN FLOW
# =============================


def run(email: str = "bot+stage@data.dnext.io") -> None:
    """Run the WTO tariff scraping workflow."""
    driver, wait = start_driver(timeout=30)
    try:
        driver.get("https://ttd.wto.org/en/download/six-digit")

        apply_filters(driver, wait)
        open_download_modal(driver, wait)

        fill_email(wait, email)
        switch_into_iframe_if_present(driver)

        fill_captcha(driver, wait)
        ensure_terms_checked(driver, wait)
        click_visible_submit_and_wait_success(driver, wait)

        logging.info("Done")

    finally:
        # If you want the browser to stay open for debugging, comment this out.
        driver.quit()


if __name__ == "__main__":
    run()
