"""Google search command for Autogpt."""
from __future__ import annotations

import json
import copy
import urllib
import tiktoken
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

import openai
from trafilatura import fetch_url, extract
from tenacity import retry, stop_after_attempt, wait_random_exponential

from selenium import webdriver
from pathlib import Path
from webdriver_manager.chrome import ChromeDriverManager
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

import numpy as np
from haversine import haversine

CFG = Config()


def load_driver():
    chromium_driver_path = Path("/usr/bin/chromedriver")

    options = ChromeOptions()
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.5615.49 Safari/537.36"
    )

    if platform == "linux" or platform == "linux2":
        options.add_argument("--disable-dev-shm-usage")
        # options.add_argument("--remote-debugging-port=9222")

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
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
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.input_box>input.input_search")))

    # normalize latitude and longitude
    lat, lng = round(latitude, 7), round(longitude, 7)
    coord = f'{lat},{lng}'

    # search for the query and click enter
    search_box = driver.find_element_by_css_selector("div.input_box>input.input_search")
    search_box.send_keys(coord)
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
    "kor_tourism_places_nearby_latlng",
    "get korea tourism place info nearby latlng. query is used to filter the results",
    '"latitude": "<latitude>", "longitude": "<longitude>", "query": "<query>"',
)
def kor_tourism_places_nearby_latlng(latitude: float, longitude: float, query: str = '') -> list:
    driver = load_driver()
    driver.get("https://map.naver.com/v5/search")

    # wait until the page is loaded
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.input_box>input.input_search")))

    if isinstance(latitude, str):
        latitude = float(latitude)
    if isinstance(longitude, str):
        longitude = float(longitude)

    lat, lng = round(latitude, 7), round(longitude, 7)
    coord = f'{lat},{lng}'

    # search for the query and click enter
    search_box = driver.find_element_by_css_selector("div.input_box>input.input_search")
    search_box.send_keys(coord)
    search_box.send_keys(Keys.ENTER)

    # wait until the page is loaded
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.XPATH, '//div[@class="end_inner place ng-star-inserted"]')))

    # 네이버 지도 기능!! -> 가볼만한 곳
    place_infos = driver.find_elements(By.XPATH, '//div[@class="end_inner place ng-star-inserted"]')
    recommended_places = place_infos[1]

    # save current url to reload
    current_url = driver.current_url

    places = recommended_places.find_elements_by_xpath('ul[@class="list_space"]/li')
    place_n = len(places)

    tourism_places = []
    for place_i in range(place_n):

        place = places[place_i]

        html_doc = place.get_attribute('outerHTML')
        soup = BeautifulSoup(html_doc, 'html.parser')

        place_name = soup.find('strong', {'class': 'space_title'}).get_text()
        place_type = soup.find('p', {'class': 'space_text'}).get_text()

        link = place.find_element_by_xpath('.//div[@class="space_thumb_box"]')
        driver.execute_script("arguments[0].click();", link)

        place_url = driver.current_url
        place_id = place_url.split('place')[-1].split('?')[0][1:]

        # wait until the page is loaded
        driver.get(current_url)

        # wait until the page is loaded
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.XPATH, '//div[@class="end_inner place ng-star-inserted"]')))

        # reload the page every time to prevent stale element reference error
        place_infos = driver.find_elements(By.XPATH, '//div[@class="end_inner place ng-star-inserted"]')
        recommended_places = place_infos[1]
        places = recommended_places.find_elements_by_xpath('ul[@class="list_space"]/li')

        tourism_places.append({
            'place_id': place_id,
            'place_name': place_name,
            'place_type': place_type,
        })

    driver.quit()

    # get place meta information
    place_infos = []
    for place in tourism_places:
        place_id = place['place_id']

        place_header = get_place_header(place_id)
        place_main_info = get_place_main_info(place_id)
        place_review = get_place_reviews(place_id, query)

        place_info = {
            'place_id': place['place_id'],
        }

        place_info.update(place_header)
        place_info.update(place_main_info)
        place_info.update(place_review)

        place_infos.append(place_info)

    return place_infos 


@command(
    "kor_tourism_places_nearby_latlng",
    "get korea tourism place info nearby latlng. query is used to filter the results",
    '"latitude": "<latitude>", "longitude": "<longitude>", "query": "<query>"',
)
def kor_tourism_places_nearby_latlng(latitude: float, longitude: float, query: str = '') -> list:
    driver = load_driver()
    driver.get("https://map.naver.com/v5/search")

    # wait until the page is loaded
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.input_box>input.input_search")))

    if isinstance(latitude, str):
        latitude = float(latitude)
    if isinstance(longitude, str):
        longitude = float(longitude)

    lat, lng = round(latitude, 7), round(longitude, 7)
    coord = f'{lat},{lng}'

    # search for the query and click enter
    search_box = driver.find_element_by_css_selector("div.input_box>input.input_search")
    search_box.send_keys(coord)
    search_box.send_keys(Keys.ENTER)

    # wait until the page is loaded
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.XPATH, '//div[@class="end_inner place ng-star-inserted"]')))

    # 네이버 지도 기능!! -> 가볼만한 곳
    place_infos = driver.find_elements(By.XPATH, '//div[@class="end_inner place ng-star-inserted"]')
    recommended_places = place_infos[1]

    # save current url to reload
    current_url = driver.current_url

    places = recommended_places.find_elements_by_xpath('ul[@class="list_space"]/li')

    tourism_places = []
    for place_i in range(len(places)):

        # reload the page every time to prevent stale element reference error
        place = places[place_i]

        html_doc = place.get_attribute('outerHTML')
        soup = BeautifulSoup(html_doc, 'html.parser')

        place_name = soup.find('strong', {'class': 'space_title'}).get_text()
        place_type = soup.find('p', {'class': 'space_text'}).get_text()

        link = place.find_element_by_xpath('.//div[@class="space_thumb_box"]')
        driver.execute_script("arguments[0].click();", link)

        place_url = driver.current_url
        place_id = place_url.split('place')[-1].split('?')[0][1:]

        # wait until the page is loaded
        driver.get(current_url)
        driver.implicitly_wait(3)

        place_infos = driver.find_elements(By.XPATH, '//div[@class="end_inner place ng-star-inserted"]')
        recommended_places = place_infos[1]
        places = recommended_places.find_elements_by_xpath('ul[@class="list_space"]/li')

        tourism_places.append({
            'place_id': place_id,
            'place_name': place_name,
            'place_type': place_type,
        })

    driver.quit()

    # get place meta information
    place_infos = []
    for place in tourism_places:
        place_id = place['place_id']

        place_header = get_place_header(place_id)
        place_main_info = get_place_main_info(place_id)
        place_review = get_place_reviews(place_id)

        place_info = {
            'place_id': place['place_id'],
        }
        place_info.update(place_header)
        place_info.update(place_main_info)
        place_info.update(place_review)

        place_infos.append(place_info)

    return place_infos 

@command(
    "get_kor_weather_info",
    "get korea weather information at lat, lng",
    '"latitude": "<latitude>", "longitude": "<longitude>"',
)
def get_kor_weather_info(latitude: float, longitude: float):
    """
    """
    driver = load_driver()
    driver.get("https://map.naver.com/v5/search")

    # wait until the page is loaded
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.input_box>input.input_search")))

    if isinstance(latitude, str):
        latitude = float(latitude)
    if isinstance(longitude, str):
        longitude = float(longitude)

    lat, lng = round(latitude, 7), round(longitude, 7)
    coord = f'{lat},{lng}'

    # search for the query and click enter
    search_box = driver.find_element_by_css_selector("div.input_box>input.input_search")
    search_box.send_keys(coord)
    search_box.send_keys(Keys.ENTER)

    # wait until the page is loaded
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.XPATH, '//div[@class="end_inner place"]')))

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


def get_place_header(place_id):

    place_url = f"https://m.place.naver.com/place/{place_id}/home"

    driver = load_driver()
    place_info = {
        'name': None,
        'type': None,
        'rating': None,
        'n_visitor_reviews': None,
        'n_blog_reviews': None,
    }
    
    driver.get(place_url)

    # explicitly wait until the page is loaded
    # driver.implicitly_wait(3)
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.place_section")))

    soup = BeautifulSoup(driver.page_source, 'html.parser')

    # name / description
    title_section = soup.find('div', {'id': '_title'})
    if title_section:
        spans = title_section.find_all('span')
        place_info['name'] = spans[0].text
        if len(spans) > 1:
            place_info['type'] = spans[1].text

    # ratings
    place_section = soup.find('div', {'class': 'place_section'})
    if place_section:
        for span in place_section.find_all('span'):
            text = span.text
            if text.startswith('별점') and (span.find('em') is not None):
                place_info['rating'] = text.replace('별점', '').strip()
            if text.startswith('방문자리뷰') and (span.find('em') is not None):
                place_info['n_visitor_reviews'] = text.replace('방문자리뷰', '').strip()
            elif text.startswith('블로그리뷰') and (span.find('em') is not None):
                place_info['n_blog_reviews'] = text.replace('블로그리뷰', '').strip()

    driver.quit()

    return place_info

def get_place_main_info(place_id):

    place_url = f"https://m.place.naver.com/place/{place_id}/home"

    driver = load_driver()
    driver.get(place_url)

    # explicitly wait until the page is loaded
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.place_section")))

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    place_info = soup.find_all('div', class_='place_section_content')
    if len(place_info) > 0:
        place_info = place_info[0]
    else:
        return {
            'description': None,
            'address': None,
            'operation_time': None,
            'price': None,
            'convenience': None,
            'homepage': None,
            'phone': None,
            'keyword': None,
        }

    # 주소
    address_tag = place_info.find('span', text='주소')
    if address_tag:
        address = address_tag.parent.next_sibling.get_text().split('지도')[0].strip()
    else:
        address = None

    # 영업 시간
    operation_time_tag = soup.find('span', text='영업시간')
    if operation_time_tag:
        operation_time = operation_time_tag.parent.next_sibling.get_text()
        operation_time = operation_time.split('펼쳐보기')
    else:
        operation_time = None

    # 가격표
    price_tag = soup.find('span', text='가격 정보 수정 제안')
    if price_tag:
        price = price_tag.parent.next_sibling.get_text()
        if price.startswith('가격표 사진을 올려주세요'):
            price = None
    else:
        price = None

    # 편의
    convenience_tag = soup.find('span', text='편의')
    if convenience_tag:
        convenience = convenience_tag.parent.next_sibling.get_text()
    else:
        convenience = None

    # 홈페이지
    homepage_tag = soup.find('span', text='홈페이지')
    if homepage_tag:
        homepage = homepage_tag.parent.next_sibling.get_text()

        # remove 블로그 and 인스타그램
        homepage = re.sub(r'블로그|인스타그램', '', homepage)
    else:
        homepage = None

    # 전화번호
    phone_tag = soup.find('span', text='전화번호')
    if phone_tag:
        phone = phone_tag.parent.next_sibling.get_text()
    else:
        phone = None

    # 키워드
    keyword_tag = soup.find('span', text='키워드')
    if keyword_tag:
        keyword = keyword_tag.parent.next_sibling.get_text()
        keyword = keyword.split('#')
        if len(keyword) > 1:
            keyword = keyword[1:]
    else:
        keyword = None

    # 설명
    description_tag = soup.find('span', text='설명')
    if description_tag:
        description = description_tag.parent.next_sibling.get_text()
    else:
        description = None

    driver.quit()

    place_info = {
        'description': description,
        'address': address,
        'operation_time': operation_time,
        'price': price,
        'convenience': convenience,
        'homepage': homepage,
        'phone': phone,
        'keyword': keyword,
    }
    return place_info

def get_place_reviews(place_id, query):
    place_url = f"https://m.place.naver.com/place/{place_id}/review/visitor"

    driver = load_driver()
    driver.get(place_url)

    # explicitly wait until the page is loaded
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.place_section")))

    soup = BeautifulSoup(driver.page_source, 'html.parser')

    sections = soup.find_all('div', class_='place_section')
    review_section = None
    for section in sections:
        header = section.find(class_='place_section_header')
        if header and header.find(string=True, recursive=False) == '리뷰':
            review_section = section
            break

    reviews = []
    if review_section:
        li_elements = review_section.find('div', {'class': 'place_section_content'}).find('ul').find_all('li')
        for li in li_elements[:5]:
            spans = li.find_all('span')
            review = ' '.join([''.join(span.find_all(string=True, recursive=False)).strip() for span in spans])[:1000]
            reviews.append(review)

    driver.quit()
    if len(reviews) > 0:
        reviews = summarize_reviews(reviews, query)
        return {
            'reviews': reviews
        }
    else:
        return {
            'reviews': None
        }


def summarize_reviews(reviews, query):
    message = create_message("\n".join(reviews), query)
    response = get_chatgpt_response([message], model='gpt-3.5-turbo', temperature=0)['content']
    return response



MODELS_INFO = {
    'gpt-3.5-turbo': {'max_tokens': 4096, 'pricing': 0.002/1000, 'tokenizer': tiktoken.get_encoding("cl100k_base"), 'tokens_per_message': 5},
    'gpt-4': {'max_tokens': 4096, 'pricing': 0.03/1000, 'tokenizer': tiktoken.get_encoding("cl100k_base"), 'tokens_per_message': 5},
}

def split_text(text, max_tokens=500, overlap=0, model='gpt-3.5-turbo'):
    tokenizer = MODELS_INFO[model]['tokenizer']
    tokens = tokenizer.encode(text)
    sid = 0

    splitted = []
    while True:
        if sid + overlap >= len(tokens):
            break
        eid = min(sid+max_tokens, len(tokens))
        splitted.append(tokenizer.decode(tokens[sid:eid]))
        sid = eid - overlap

    return splitted

def truncate_messages(messages, system_prompt="", model='gpt-3.5-turbo', n_response_tokens=500, keep_last=False):

    max_tokens = MODELS_INFO[model]['max_tokens']
    n_tokens_per_message = MODELS_INFO[model]['tokens_per_message']
    tokenizer = MODELS_INFO[model]['tokenizer']

    n_used_tokens = 3 + n_response_tokens
    n_used_tokens += n_tokens_per_message + len(tokenizer.encode(system_prompt))

    iterator = range(len(messages))
    if keep_last: 
        iterator = reversed(iterator)

    for i in iterator:
        message = messages[i]
        n_used_tokens += n_tokens_per_message
        if n_used_tokens >= max_tokens:
            messages = messages[i+1:] if keep_last else messages[:i]
            print('Messages Truncated')
            break

        content_tokens = tokenizer.encode(message['content'])
        n_content_tokens = len(content_tokens)
        n_used_tokens += n_content_tokens
        if n_used_tokens >= max_tokens:
            truncated_content_tokens = content_tokens[n_used_tokens-max_tokens:] if keep_last else content_tokens[:max_tokens-n_used_tokens]
            other_messages = messages[i+1:] if keep_last else messages[:i]
            messages = [{'role': message['role'], 'content': tokenizer.decode(truncated_content_tokens)}] + other_messages
            print('Messages Truncated')
            break

    return messages

@retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(6))
def get_chatgpt_response(messages:list, system_prompt="", model='gpt-3.5-turbo', temperature=0.5, keep_last=True):
    messages = copy.deepcopy(messages)
    messages = truncate_messages(messages, system_prompt, model, keep_last=keep_last)
    messages = [{"role": "system", "content": system_prompt}]+messages
    completion = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    response = dict(completion.choices[0].message)
    response['dollars_spent'] = completion['usage']['total_tokens'] * MODELS_INFO[model]['pricing']

    return response



def create_message(chunk: str, question: str):
    if question != '':
        content = f'"""{chunk}""" Using the above text, answer the following'
        f' question: "{question}" -- if the question cannot be answered using the text,'
        " summarize the text. Please output in the language used in the above text.",
    else:
        content = (
            f'"""{chunk}"""'
            '\nSummarize above reviews.'
        )
    
    return {
        "role": "user",
        "content": content
    }