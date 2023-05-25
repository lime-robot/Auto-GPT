from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options as ChromeOptions

from webdriver_manager.chrome import ChromeDriverManager
from sys import platform


chromium_driver_path = Path("/usr/bin/chromedriver")

options = ChromeOptions()
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.5615.49 Safari/537.36"
)

if platform == "linux" or platform == "linux2":
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--remote-debugging-port=9222")

options.add_argument("--no-sandbox")
chromium_driver_path = Path("/usr/bin/chromedriver")

driver = webdriver.Chrome(
    executable_path=chromium_driver_path
    if chromium_driver_path.exists()
    else ChromeDriverManager().install(),
    options=options,
)

print('success to load driver')