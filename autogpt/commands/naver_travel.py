"""Google search command for Autogpt."""
from __future__ import annotations

import json
import urllib
from urllib.request import Request, urlopen

import re
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options as ChromeOptions

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from webdriver_manager.chrome import ChromeDriverManager
from sys import platform

import time
from bs4 import BeautifulSoup
import requests

from duckduckgo_search import ddg

from autogpt.commands.command import command
from autogpt.config import Config
#import os
import requests

CFG = Config()


def load_driver():
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
    return driver

@command(
    "latlng2kor_address",
    "convert latitude and longitude to korean address",
    '"latitude": "<latitude>", "longitude": "<longitude>"',
)
def latlng2kor_address(latitude: float, longitude: float) -> str:
    """
    latitdue and longitude to address 지번, 도로명
    """
    driver = load_driver()
    driver.get("https://map.naver.com/v5/search")

    # wait until the page is loaded
    driver.implicitly_wait(3)

    # normalize latitude and longitude
    lat, lng = round(latitude, 7), round(longitude, 7)
    location_str = f'{lat},{lng}'

    # search for the query and click enter
    search_box = driver.find_element_by_css_selector("div.input_box>input.input_search")
    search_box.send_keys(location_str)
    search_box.send_keys(Keys.ENTER)

    try:
        address_jibun = driver.find_element(By.XPATH, '//div[@class="end_box"]/a[@class="end_title"]').text
    except:
        address_jibun = None
    try:
        address_road = driver.find_element(By.XPATH, '//div[@class="end_box"]/span[@class="end_title subtitle ng-star-inserted"]').text
        # remove 도로명 from address_road
        address_road = address_road[3:]
    except:
        address_road = None

    address = {
        'address_jibun': address_jibun,
        'address_road': address_road
    }
    return json.dumps(address, ensure_ascii=False)


@command(
    "kor_address2latlng",
    "convert korean address(ex: jibun(지번), road(도로명) etc) to latitude and longitude",
    '"address": "<address>"',
)
def kor_address2latlng(address):
    client_id = CFG.naver_api_id
    client_secret = CFG.naver_api_client_secret 
    url = f"https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode?query=" \
    			+ urllib.parse.quote(address)
    
    request = urllib.request.Request(url)
    request.add_header('X-NCP-APIGW-API-KEY-ID', client_id)
    request.add_header('X-NCP-APIGW-API-KEY', client_secret)
    response = urlopen(request)
    res = response.getcode()
    
    if (res == 200):
        response_body = response.read().decode('utf-8')
        response_body = json.loads(response_body)

        if response_body['meta']['totalCount'] == 1 : 
            lng = response_body['addresses'][0]['x']
            lat = response_body['addresses'][0]['y']
            
            return {
                'lat': lat,
                'lng': lng,
            }
        else:
            print('address does not exist')
        
    else:
        print(f'address: {address} Error Code: {res}')



@command(
    "get_weather_info_at_kor_address",
    "get weather information at korean address(ex: jibun(지번), road(도로명) etc)",
    '"address": "<address>"',
)
def get_weather_info_at_kor_address(address):
    """
    address: 도로명, 지번
    """
    driver = load_driver()
    driver.get("https://map.naver.com/v5/search")

    # wait until the page is loaded
    driver.implicitly_wait(3)

    # search for the query and click enter
    search_box = driver.find_element_by_css_selector("div.input_box>input.input_search")
    search_box.send_keys(address)
    search_box.send_keys(Keys.ENTER)
    place_infos = driver.find_elements(By.XPATH, '//div[@class="end_inner place"]')
    weather_info = place_infos[0].get_attribute('outerHTML')

    soup = BeautifulSoup(weather_info, 'html.parser')

    weather_data = {}

    current_box = soup.find('div', {'class': 'current_box'})
    weather_data['current_temperature'] = current_box.find('span', {'class': 'temperature'}).text
    weather_data['current_status'] = current_box.find('span', {'class': 'today_subtitle'}).text
    weather_data['current_wind'] = current_box.find('dd', {'class': 'measure_text'}).text

    weekly_box = soup.find('table')
    days = [th.text for th in weekly_box.find_all('th')]
    weather_statuses = [td.find('span').text for td in weekly_box.find_all('td')]
    temperatures = [td.find('div', {'class': 'week_text_box'}).text for td in weekly_box.find_all('td')]

    weather_data['weekly'] = []
    for day, status, temperature in zip(days, weather_statuses, temperatures):
        weather_data['weekly'].append({
            'day': day,
            'status': status,
            'temperature': temperature,
        })

    # output in JSON format
    return json.dumps(weather_data, ensure_ascii=False)