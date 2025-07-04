import json
import os
import re
import shutil
import subprocess
import sys
import time
from packaging import version

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CHROME_DRIVER_PATH = '/usr/local/bin/chromedriver'
CHROME_JSON_URL = 'https://googlechromelabs.github.io/chrome-for-testing/latest-versions-per-milestone-with-downloads.json'

# === CONFIG - Edit for your own Shopify/testing info ===
STORE_URL = 'https://theventashop.com/'
SHIPPING_INFO = {
    'email': 'test@example.com',
    'first_name': 'John',
    'last_name': 'Doe',
    'address1': '123 Elm Street',
    'city': 'Los Angeles',
    'country': 'United States',
    'province': 'California',
    'zip': '90001',
    'phone': '1234567890'
}
PAYMENT_INFO = {
    'card_number': '5489010373940608',  # test card
    'name_on_card': 'John Doe',
    'expiry': '12/34',
    'cvv': '123'
}

def get_chrome_version():
    cmds = ['google-chrome --version', 'chromium-browser --version', 'chromium --version']
    for cmd in cmds:
        try:
            output = subprocess.check_output(cmd.split()).decode('utf-8')
            match = re.search(r'(\d+\.\d+\.\d+)', output)
            if match:
                return match.group(1)
        except Exception:
            continue
    print("Could not detect Chrome version.")
    sys.exit(1)

def download_and_install_chromedriver(driver_url):
    zip_path = '/tmp/chromedriver_linux64.zip'
    print(f"Downloading ChromeDriver from {driver_url} ...")
    r = requests.get(driver_url, stream=True)
    with open(zip_path, 'wb') as f:
        shutil.copyfileobj(r.raw, f)
    print("Download complete.")

    print("Unzipping...")
    subprocess.run(['unzip', '-o', zip_path, '-d', '/tmp/'], check=True)

    print(f"Moving chromedriver to {CHROME_DRIVER_PATH}")
    shutil.move('/tmp/chromedriver', CHROME_DRIVER_PATH)
    os.chmod(CHROME_DRIVER_PATH, 0o755)
    print("ChromeDriver installed successfully.")

def install_best_chromedriver():
    chrome_ver = get_chrome_version()
    major_ver = int(chrome_ver.split('.')[0])
    print(f"Detected Chrome version: {chrome_ver} (major: {major_ver})")

    print(f"Fetching ChromeDriver versions JSON...")
    resp = requests.get(CHROME_JSON_URL)
    data = resp.json()

    milestones_list = data.get('milestones')
    if not milestones_list:
        print("JSON format changed, 'milestones' key not found.")
        sys.exit(1)

    suitable = [m for m in milestones_list if int(m['milestone']) <= major_ver and m['downloads'].get('chromedriver')]
    if not suitable:
        print("No suitable ChromeDriver versions found for your Chrome version.")
        sys.exit(1)

    best_version = max(suitable, key=lambda m: version.parse(m['version']))
    milestone = int(best_version['milestone'])
    print(f"Best matching milestone: {milestone} (version {best_version['version']})")
    chromedriver_downloads = best_version['downloads']['chromedriver']
    linux64_download = next((d for d in chromedriver_downloads if d['platform'] == 'linux64'), None)
    if not linux64_download:
        print(f"No linux64 ChromeDriver download found for milestone {milestone}.")
        sys.exit(1)

    driver_url = linux64_download['url']
    download_and_install_chromedriver(driver_url)

def init_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--remote-debugging-port=9222")
    driver = webdriver.Chrome(CHROME_DRIVER_PATH, options=options)
    return driver

def get_cheapest_product(driver):
    driver.get(STORE_URL)
    time.sleep(3)
    products = driver.find_elements(By.CSS_SELECTOR, 'a.full-unstyled-link')
    product_data = []
    for product in products:
        title = product.text.strip()
        if not title:
            continue
        try:
            price_element = product.find_element(By.XPATH, './/following-sibling::*[contains(text(), "$")]')
            price_text = price_element.text.strip()
            price = float(price_text.replace('$', '').replace(',', ''))
            link = product.get_attribute('href')
            product_data.append({'title': title, 'price': price, 'link': link})
        except Exception:
            continue
    if not product_data:
        raise Exception("No products found")
    cheapest = min(product_data, key=lambda x: x['price'])
    return cheapest

def add_product_to_cart(driver, product_link):
    driver.get(product_link)
    wait = WebDriverWait(driver, 10)
    add_to_cart_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[name="add"]')))
    add_to_cart_btn.click()
    time.sleep(3)
    driver.get(STORE_URL + '/cart')
    time.sleep(2)
    checkout_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[name="checkout"], a[href*="/checkouts/"]')))
    checkout_btn.click()
    time.sleep(3)

def fill_shipping_info(driver):
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.ID, 'checkout_email')))
    driver.find_element(By.ID, 'checkout_email').send_keys(SHIPPING_INFO['email'])
    driver.find_element(By.ID, 'checkout_shipping_address_first_name').send_keys(SHIPPING_INFO['first_name'])
    driver.find_element(By.ID, 'checkout_shipping_address_last_name').send_keys(SHIPPING_INFO['last_name'])
    driver.find_element(By.ID, 'checkout_shipping_address_address1').send_keys(SHIPPING_INFO['address1'])
    driver.find_element(By.ID, 'checkout_shipping_address_city').send_keys(SHIPPING_INFO['city'])
    driver.find_element(By.ID, 'checkout_shipping_address_zip').send_keys(SHIPPING_INFO['zip'])
    driver.find_element(By.ID, 'checkout_shipping_address_phone').send_keys(SHIPPING_INFO['phone'])
    country = driver.find_element(By.ID, 'checkout_shipping_address_country')
    country.send_keys(SHIPPING_INFO['country'])
    province = driver.find_element(By.ID, 'checkout_shipping_address_province')
    province.send_keys(SHIPPING_INFO['province'])
    continue_btn = driver.find_element(By.CSS_SELECTOR, 'button[name="button"]')
    continue_btn.click()
    time.sleep(5)

def fill_payment_info(driver):
    wait = WebDriverWait(driver, 15)
    iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'iframe[name^="card-fields"]')))
    driver.switch_to.frame(iframe)
    driver.find_element(By.NAME, 'number').send_keys(PAYMENT_INFO['card_number'])
    driver.find_element(By.NAME, 'name').send_keys(PAYMENT_INFO['name_on_card'])
    driver.find_element(By.NAME, 'expiry').send_keys(PAYMENT_INFO['expiry'])
    driver.find_element(By.NAME, 'verification_value').send_keys(PAYMENT_INFO['cvv'])
    driver.switch_to.default_content()
    pay_btn = wait.until(EC.element_to_be_clickable((By.ID, 'continue_button')))
    pay_btn.click()
    time.sleep(10)

def main():
    install_best_chromedriver()
    driver = init_driver()
    try:
        cheapest = get_cheapest_product(driver)
        print(f"Cheapest product: {cheapest['title']} at ${cheapest['price']}")
        add_product_to_cart(driver, cheapest['link'])
        fill_shipping_info(driver)
        fill_payment_info(driver)
        print("Checkout automation complete!")
    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == '__main__':
    main()
