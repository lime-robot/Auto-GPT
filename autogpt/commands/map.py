"""Map."""
from __future__ import annotations

import os
import re
import requests
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor
from autogpt.commands.command import command
from autogpt.config import Config
from autogpt.llm.llm_utils import create_chat_completion
from . import URL_MEMORY

CFG = Config()


def get_kakao_review(place_url):
    options = webdriver.ChromeOptions()
    options.add_argument('headless')

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), 
        options=options
    )

    # construct mobile comment url in kakao
    place_url = place_url.split("/")
    place_url.insert(-1, 'm')
    place_url = "/".join(place_url)
    place_url += "#comment"

    # get mobile url
    driver.get(place_url)

    # 카카오맵 열기 버튼 삭제
    element = WebDriverWait(driver, 3).until(
        EC.element_to_be_clickable(
        (By.CSS_SELECTOR, '#kakaoWrap > div.floating_bnr.hide > div > a.btn_close')
    ))
    element.click()

    logit = 0
    try:
        reviews = (
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "list_grade"))
            )
            .find_elements(By.CSS_SELECTOR, 'li > div.inner_grade > div.comment_info > p > span')
        )
    except Exception as e:
        print(e, place_url)
        reviews = []
    reviews = sorted([v.text for v in reviews if v.text != ''], key=len, reverse=True)[:3]

    driver.quit()
    return reviews
