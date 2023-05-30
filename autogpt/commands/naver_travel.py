"""Google search command for Autogpt."""
from __future__ import annotations

import os
import random
import json
import concurrent.futures
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
    False # FIXME: disabled because google search is better
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
    False, # FIXME: disabled due to slow and buggy performance
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
        place_info = {
            'place_id': place['place_id'],
        }
        place_info.get_place_info(place_id, query)

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

def get_place_info(place_id, query=None):
    place_url = f"https://m.place.naver.com/place/{place_id}/home"

    driver = load_driver()
    place_info = {
        # header
        'name': None,
        'type': None,
        'rating': None,
        'n_visitor_reviews': None,
        'n_blog_reviews': None,

        # main
        'description': None,
        'address': None,
        'operation_time': None,
        'price': None,
        'convenience': None,
        'homepage': None,
        'phone': None,
        'keyword': None,

        # review
        'reviews': None,
    }
    
    driver.get(place_url)

    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.place_section")))
    html = driver.page_source

    place_info.update(get_place_header(html))
    place_info.update(get_place_main_info(html))
    place_info.update(get_place_reviews(place_id, query))

    driver.quit()

    return place_info


def get_place_header(html):
    soup = BeautifulSoup(html, 'html.parser')

    place_info = {}

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

    return place_info

def get_place_main_info(html):
    soup = BeautifulSoup(html, 'html.parser')

    place_info = {}
    place_section = soup.find_all('div', class_='place_section_content')
    if not len(place_section) > 0:
        return place_info

    # 주소
    address_tag = soup.find('span', text='주소')
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

# def get_place_reviews(html, query=None):
#     soup = BeautifulSoup(html, 'html.parser')

#     sections = soup.find_all('div', class_='place_section')
#     review_section = None
#     for section in sections:
#         header = section.find(class_='place_section_header')
#         if header and header.find(string=True, recursive=False) == '리뷰':
#             review_section = section
#             break

#     reviews = []
#     if review_section:
#         li_elements = review_section.find('div', {'class': 'place_section_content'}).find('ul').find_all('li')
#         for li in li_elements[:5]:
#             spans = li.find_all('span')
#             review = ' '.join([''.join(span.find_all(string=True, recursive=False)).strip() for span in spans])[:1000]
#             reviews.append(review)

#     if len(reviews) > 0:
#         if query is not None:
#             reviews = summarize_reviews(reviews, query)
#         return {
#             'reviews': reviews
#         }
#     else:
#         return {
#             'reviews': None
#         }

def get_place_reviews(place_id, query=None):
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
        if query is not None:
            reviews = summarize_reviews(reviews, query)
        return {
            'reviews': reviews
        }
    else:
        return {
            'reviews': None
        }


def summarize_reviews(texts, query):
    message = create_message_reviews("\n".join(texts), query)
    response = get_chatgpt_response([message], model='gpt-3.5-turbo', temperature=0)['content']
    return response

def create_message_place_infos(chunk: str, question: str):
    if question != '':
        content = (
            # "YOU MUST ANSWER WITH info of ['name', 'place_id', 'latitude', 'longitude'] of each place"
            # " this MUST BE LOCATED IN FRONT OF TEXT!!! and the summarize or query answer should follow."
            f' """{chunk}""" Using the above text, answer the following'
            f' question: "{question}" -- if the question cannot be answered using the text,'
            " summarize the text. Please output in the language used in the above text."
        )
    else:
        content = (
            # "YOU MUST ANSWER WITH info of ['name', 'place_id', 'latitude', 'longitude'] of each place"
            # " this MUST BE LOCATED IN FRONT OF TEXT!!! and the summarize or query answer should follow."
            f' """{chunk}"""'
            '\nSummarize above place informations.'
        )
    
    return {
        "role": "user",
        "content": content
    }

def summarize_place_infos(texts, query):
    message = create_message_place_infos(texts, query)
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



def create_message_reviews(chunk: str, question: str):
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


# getting detailed informations of a place
# types
K2E_TYPES = {
    '음식점': 'DINING',
    '카페': 'CAFE',
    '쇼핑': 'SHOPPING',
    '숙박': 'ACCOMMODATION',
    '병원의료': 'HOSPITAL',
    '은행': 'BANK',
    '주유소': 'OIL',
    '마트슈퍼': 'MART',
    '편의점': 'STORE',
    '생활편의': 'CONVENIENCE',
    '명소': 'SIGHTS',
    '체육시설': 'SPORTS',
    '영화공연': 'CINEMA',
    '관광서': 'GOVERNMENT',
}
E2K_TYPES = {v: k for k, v in K2E_TYPES.items()}


DESC_OF_NEARBY = (
    "find korean place nearby lat and lng, you can speficify place type and query"
    " place_type: [DINING, CAFE, SHOPPING, ACCOMMODATION, HOSPITAL, BANK, OIL, MART, STORE, CONVENIENCE, SIGHTS, SPORTS, CINEMA, GOVERNMENT]"
    " goal: is a <GOAL> chosen by user"
    " sort: 0: related sort(recommended), 1: distance sort (close to far)"
    " max_results: choose number reasonable for your query, default is 8"
)
@command(
    "kor_nearby_search_details",
    DESC_OF_NEARBY,
    '"latitude": "<latitude>", "longitude": "<longitude>", "place_type": "<place_type>", "sort": "<sort>", "goal": "<goal>", "max_results": "<max_results>"',
    False, # FIXME: disabled because it's supports too huge information
)
def kor_nearby_search_details(latitude, longitude, place_type, sort, goal, max_results=8):
    query = goal

    driver = load_driver()

    place_type = place_type.upper()
    lat, lng = round(latitude, 7), round(longitude, 7)

    # 0: 관련도 순, 1: 거리 순
    sort = int(sort)
    coord = f'{lng};{lat}'

    naver_nearby_url = f"https://m.map.naver.com/search2/interestSpot.naver?type={place_type}&searchCoord={coord}&siteSort={sort}&sm=clk"
    driver.get(naver_nearby_url)

    # wait for loading
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'li._item._lazyImgContainer')))
    elements = driver.find_elements_by_css_selector('li._item._lazyImgContainer')[:max_results]

    def get_place_infos_nearby_search(element):
        place_id = element.get_attribute('data-id')

        place_info = {
            'place_id': place_id,
            'longitude': element.get_attribute('data-longitude'),
            'latitude': element.get_attribute('data-latitude'),
        }
        place_info.update(get_place_info(place_id))

        return place_info

    with concurrent.futures.ThreadPoolExecutor(len(elements)) as executor:
        results = list(executor.map(get_place_infos_nearby_search, elements))

    return results


DESC_OF_NEARBY_SUMMARY = (
    "find korean place nearby lat and lng and return the summary report, you can speficify place type and query"
    " place_type: [DINING, CAFE, SHOPPING, ACCOMMODATION, HOSPITAL, BANK, OIL, MART, STORE, CONVENIENCE, SIGHTS, SPORTS, CINEMA, GOVERNMENT]"
    " goal: is a <GOAL> chosen by user"
    " sort: 0: related sort(recommended), 1: distance sort (close to far)"
    " max_results: choose number reasonable for your query, default is 8"
)
@command(
    "kor_nearby_search_summary",
    DESC_OF_NEARBY_SUMMARY,
    '"latitude": "<latitude>", "longitude": "<longitude>", "place_type": "<place_type>", "sort": "<sort>", "goal": "<goal>", "max_results": "<max_results>"',
    False, # FIXME: this command doens't return proper summary information so it's disabled
)
def kor_nearby_search_summary(latitude, longitude, place_type, sort, goal, max_results=8):
    query = goal

    driver = load_driver()

    place_type = place_type.upper()
    lat, lng = round(latitude, 7), round(longitude, 7)

    # 0: 관련도 순, 1: 거리 순
    sort = int(sort)
    coord = f'{lng};{lat}'

    naver_nearby_url = f"https://m.map.naver.com/search2/interestSpot.naver?type={place_type}&searchCoord={coord}&siteSort={sort}&sm=clk"
    driver.get(naver_nearby_url)

    # wait for loading
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'li._item._lazyImgContainer')))
    elements = driver.find_elements_by_css_selector('li._item._lazyImgContainer')[:max_results]

    def get_place_infos_nearby_search(element):
        place_id = element.get_attribute('data-id')

        place_info = {
            'place_id': place_id,
            'longitude': element.get_attribute('data-longitude'),
            'latitude': element.get_attribute('data-latitude'),
        }
        place_info.update(get_place_info(place_id))

        return place_info

    with concurrent.futures.ThreadPoolExecutor(len(elements)) as executor:
        results = list(executor.map(get_place_infos_nearby_search, elements))

    # final report
    place_report = json.dumps(results, ensure_ascii=True)
    if query is not None:
        summarized_report = summarize_place_infos(place_report, query)

        # get each places ['name', 'place_id', 'latitude', 'longitude']
        final_report = []
        for place in results:
            final_report.append({
                'name': place['name'],
                'place_id': place['place_id'],
                'latitude': place['latitude'],
                'longitude': place['longitude'],
            })

        final_report = json.dumps(final_report, ensure_ascii=True)
        final_report += '\n'
        final_report += summarized_report
    else:
        final_report = place_report

    return final_report


def create_message_for_rating_place(place_info: str, goal: str):
    content = (
        f'you will have to rate how good is this place from 1.0 to 10.0 related to the goal: [ "{goal}" ]'
        f' the detailed info of place is following [ {place_info} ]'
        ' after rating the place please explain why you rated the place like that.'
        ' the output format should be like this: [ "<your rate>|<the reason why you rate to that score>" ]'
        " please output in the language used in given text."
        " write the reason with clear and prominent evidence"
        " Use enough text you want but there MUST not be unnecessary text."
    )
    
    return {
        "role": "user",
        "content": content
    }

def rate_place_infos_gpt3(place_info, goal):
    message = create_message_for_rating_place(place_info, goal)
    response = get_chatgpt_response([message], model='gpt-3.5-turbo', temperature=0)['content']
    return response

def rate_place_infos_gpt4(place_info, goal):
    message = create_message_for_rating_place(place_info, goal)
    response = get_chatgpt_response([message], model='gpt-4', temperature=0)['content']
    return response


def create_message_for_ranking_places_v2(place_infos: str, goal: str):
    """adding relative rating & ranking opinion"""
    content = (
        ' you already gave impression of each place when you look at it'
        f' the detailed review of places by you is following [ {place_infos} ]'
        ' now you have to make ranking of among this places from 1 to the last which seems'
        f' most related to the goal: [ "{goal}" ]'
        ' Also rerate the places for relative score, the highest is 10.0 and lowest should be 0.0'
        ' support reason in short for each place why you ranked and rerate like that considering goal'
        ' the output format should be like is in dict format: [ {<place_id>: <relative rate>|<rank>|<the reason why you rate and rank like that>, ...: ... } ]'
        ' Remember. This is a relative opinion of you so MUST be made by considering all the place information given'
        " please output in the language used in given text."
        ' strictly follow the output format and do not print out anything else.'
    )
    
    return {
        "role": "user",
        "content": content
    }

def create_message_for_ranking_places(place_infos: str, goal: str):
    content = (
        ' you already gave impression of each place when you look at it'
        f' the detailed review of places by you is following [ {place_infos} ]'
        ' now you have to make ranking of among this places from 1 to the last which seems'
        ' highest related place to the goal should be 1st and lowest related place should be last'
        f' most related to the goal: [ "{goal}" ]'
        ' the output format should be like this in dict format: [ {place_id}: {rank}, {place_id}: {rank}, ..." ]'
        " please output in the language used in given text."
        ' strictly follow the output format and do not print out anything else.'
    )
    
    return {
        "role": "user",
        "content": content
    }

def rank_place_infos_gpt3(place_infos, goal):
    message = create_message_for_ranking_places(place_infos, goal)
    response = get_chatgpt_response([message], model='gpt-3.5-turbo', temperature=0)['content']
    return response

def rank_place_infos_gpt4(place_infos, goal):
    message = create_message_for_ranking_places(place_infos, goal)
    response = get_chatgpt_response([message], model='gpt-4', temperature=0)['content']
    return response


DESC_OF_NEARBY_SUMMARY_RANK = (
    "find korean place nearby lat and lng and return the summary report and save detail info to file"
    " you MUST input proper <project_name> in english to save the detail info to file"
    " the filename will be chosen automatically with format f'place_info_<place_id>.json' and saved to <project_name>/place_info_<place_id>.json"
    " you will get returned <place_id> so you can further use it to get detail info"
    " don't choose work_dir and project name randomly. this names should be unique and related to the data your are collecting"
    " this detailed report will include also the ranking of each places"
    " place_type: [DINING, CAFE, SHOPPING, ACCOMMODATION, HOSPITAL, BANK, OIL, MART, STORE, CONVENIENCE, SIGHTS, SPORTS, CINEMA, GOVERNMENT]"
    " goal: is a <GOAL> chosen by user what user want to achieve"
    " sort: 0: related sort(recommended), 1: distance sort (close to far)"
    " max_results: choose number reasonable for the goal"
)
@command(
    "kor_nearby_search_summary_and_save_details_to_file",
    DESC_OF_NEARBY_SUMMARY_RANK,
    '"latitude": "<latitude>", "longitude": "<longitude>", "place_type": "<place_type>", "sort": "<sort>", "goal": "<goal>", "project_name": <project_name>, "max_results": "<max_results>"',
)
def kor_nearby_search_summary_and_save_details_to_file(latitude, longitude, place_type, sort, goal, project_name, max_results):
    query = goal

    repo_work_dir = os.path.join(Path.cwd(), 'autogpt/auto_gpt_workspace')
    save_dir = os.path.join(repo_work_dir, project_name)

    if not Path(save_dir).exists():
        os.makedirs(save_dir, exist_ok=True)

    driver = load_driver()

    place_type = place_type.upper()
    lat, lng = round(latitude, 7), round(longitude, 7)

    # 0: 관련도 순, 1: 거리 순
    sort = int(sort)
    coord = f'{lng};{lat}'

    naver_nearby_url = f"https://m.map.naver.com/search2/interestSpot.naver?type={place_type}&searchCoord={coord}&siteSort={sort}&sm=clk"
    driver.get(naver_nearby_url)

    # wait for loading
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'li._item._lazyImgContainer')))
    elements = driver.find_elements_by_css_selector('li._item._lazyImgContainer')[:max_results]

    def get_place_infos_nearby_search(element):
        place_id = element.get_attribute('data-id')

        place_info = {
            'place_id': place_id,
            'longitude': element.get_attribute('data-longitude'),
            'latitude': element.get_attribute('data-latitude'),
        }
        place_info.update(get_place_info(place_id))

        return place_info

    with concurrent.futures.ThreadPoolExecutor(len(elements)) as executor:
        results = list(executor.map(get_place_infos_nearby_search, elements))

    # search by order
    # results = []
    # for element in elements:
    #     # random waiting time to avoid blocking
    #     time.sleep(random.uniform(0.5, 1.5))

    #     results.append(get_place_infos_nearby_search(element))

    place_detail_infos = []
    place_summary_infos = []
    for place in results:
        # type ex ) DINING, 중식당
        save_type = f"{place_type}, {place['type']}"

        place_summary_info = {
            'place_id': place['place_id'],
            'type': save_type,
            'latitude': place['latitude'],
            'longitude': place['longitude'],
            'rating': None,
            'rank': None,
        }
        place_info = json.dumps(place, ensure_ascii=False)

        try:
            rate_result = rate_place_infos_gpt3(place_info, query)
            rating, rate_result = rate_result.split('|')

            # rating must be float and between 0 and 10
            assert 0 <= float(rating) <= 10
        except:
            rate_result = rate_place_infos_gpt4(place_info, query)
            rating, rate_result = rate_result.split('|')

            # rating must be float and between 0 and 10
            assert 0 <= float(rating) <= 10

        # save whole detail data
        place_detail_info = copy.deepcopy(place)
        place_detail_info['type'] = save_type
        place_detail_info['rating'] = rating
        place_detail_info['rate_reason'] = rate_result
        place_detail_infos.append(place_detail_info)

        # each place info 
        place_summary_info['rating'] = rating
        place_summary_info['rate_reason'] = rating
        place_summary_infos.append(place_summary_info)

    # rank the places
    place_infos = json.dumps(place_summary_infos)
    try:
        rank_results = rank_place_infos_gpt3(place_infos, query)
        rank_results = json.loads(rank_results)

        # for v2
        # the output format should be in dict format: [ {place_id}: "{rate}|{rank}", ... ]
        # check the format rate which MUST be between 0. and 10.
        # for rate_rank in rank_results.values():
        #     rate, rank, reason = rate_rank.split('|')
        #     assert 0 <= float(rate) <= 10
    except:
        rank_results = rank_place_infos_gpt4(place_infos, query)
        rank_results = json.loads(rank_results)

        # for v2
        # the output format should be in dict format: [ {place_id}: "{rate}|{rank}", ... ]
        # check the format rate which MUST be between 0. and 10.
        # for rate_rank in rank_results.values():
        #     rate, rank, reason = rate_rank.split('|')
        #     assert 0 <= float(rate) <= 10

    # update the rank
    # each place
    place_n = len(place_summary_infos)
    for summary in place_summary_infos:
        if summary['place_id'] in rank_results:
            # rate, rank, reason = rank_results[summary['place_id']].split('|')
            # rate, rank = float(rate), int(rank)
            rank = rank_results[summary['place_id']]
        else:
            # rate, rank, reason = -1, -1, ''
            rank = -1
        
        summary['rank'] = f"{rank}/{place_n}"

        # rating by comparing with other places
        # summary['relative_rating'] = rate

        # to save memory
        del summary['rate_reason']

    # save detail data
    for detail in place_detail_infos:
        filename = f"place_info_{detail['place_id']}.json"
        if detail['place_id'] in rank_results:
            # rate, rank, reason = rank_results[detail['place_id']].split('|')
            # rate, rank = float(rate), int(rank)
            rank = rank_results[detail['place_id']]
        else:
            # rate, rank, reason = -1, -1, ''
            rank = -1

        detail['rank'] = f"{rank}/{place_n}"
        # detail['relative_rating'] = rate
        # detail['rank_reason'] = reason

        detail = json.dumps(detail, ensure_ascii=False)

        with open(f"{save_dir}/{filename}", 'w') as f:
            f.write(detail)

    place_summary_infos = json.dumps(place_summary_infos, ensure_ascii=True)
    return place_summary_infos



@command(
    "distance_matrix",
    (
        "caculate distance matrix between places based on latitude and longitude. return matrix in meter and kilometer",
        "data type should be - list(list(float, float)), ex) [[lat1, lng1], [lat2, lng2], ...]"
    ),
    "coords: <coords>"
)
def distance_matrix(coords: list(list(float, float))):
    place_n = len(coords)
    m_distances = np.zeros((place_n, place_n))
    km_distances = np.zeros((place_n, place_n))
    for i in range(place_n):
        for j in range(place_n):
            loc_i = (float(coords[i][0]), float(coords[i][1]))
            loc_j = (float(coords[j][0]), float(coords[j][1]))
            m_distances[i, j] = haversine(loc_i, loc_j, unit='m')
            km_distances[i, j] = haversine(loc_i, loc_j, unit='km')

    m_dist_mat = np.array2string(m_distances, precision=1, floatmode='fixed')
    km_dist_mat = np.array2string(km_distances, precision=1, floatmode='fixed')

    return {
        'm_distances': m_dist_mat,
        'km_distances': km_dist_mat,
    }


@command(
    "get_optimal_route_5_for_car",
    (
        "get optimal route for car, start and goal must be tuple of (lng, lat)"
        "waypoints must be list of tuple of (lng, lat) and optional and max 5 waypoints are allowed"
    ),
    "start: <start>, goal: <goal>, waypoints: <waypoints>, option: <option>"
)
def get_optimal_route_5_for_car(start, goal, waypoints=None, option=''):
    assert start, 'start must be a tuple of (lng, lat)'
    assert goal, 'goal must be a tuple of (lng, lat)'

    assert len(start) == 2, 'start must be a tuple of (lng, lat)'
    assert len(goal) == 2, 'goal must be a tuple of (lng, lat)'

    waypoints = '|'.join([f"{point[0]},{point[1]}" for point in waypoints]) if waypoints else ''
    url = f"https://naveropenapi.apigw.ntruss.com/map-direction/v1/driving?start={start[0]},{start[1]}&goal={goal[0]},{goal[1]}&waypoints={waypoints}&option={option}"

    client_id = CFG.naver_api_id
    client_secret = CFG.naver_api_client_secret
    
    request = urllib.request.Request(url)
    request.add_header('X-NCP-APIGW-API-KEY-ID', client_id)
    request.add_header('X-NCP-APIGW-API-KEY', client_secret)
    
    response = urllib.request.urlopen(request)
    rescode = response.getcode()
    
    if (rescode == 200):
        response_body = response.read().decode('utf-8')
        route = json.loads(response_body)

        paths = route['route']['traoptimal'][0]['path']

        # due to token limit, only left 5 path points including start & end
        # only left 5 path points including start & end
        paths = paths[::len(paths)//5] + [paths[-1]]
        route['route']['traoptimal'][0]['path'] = paths

        del route['route']['traoptimal'][0]['summary']
        del route['route']['traoptimal'][0]['section']
        del route['route']['traoptimal'][0]['guide']

        return route
    else:
        return f'start: {start} goal: {goal}, waypoints: {waypoints}, Error Code: {rescode}'


@command(
    "get_optimal_route_15_for_car",
    (
        "get optimal route for car, start and goal must be tuple of (lng, lat)"
        "waypoints must be list of tuple of (lng, lat) and optional and max 15 waypoints are allowed"
    ),
    "start: <start>, goal: <goal>, waypoints: <waypoints>, option: <option>"
)
def get_optimal_route_15_for_car(start, goal, waypoints=None, option=''):
    assert start, 'start must be a tuple of (lng, lat)'
    assert goal, 'goal must be a tuple of (lng, lat)'

    assert len(start) == 2, 'start must be a tuple of (lng, lat)'
    assert len(goal) == 2, 'goal must be a tuple of (lng, lat)'

    waypoints = '|'.join([f"{point[0]},{point[1]}" for point in waypoints]) if waypoints else ''
    url = f"https://naveropenapi.apigw.ntruss.com/map-direction-15/v1/driving?start={start[0]},{start[1]}&goal={goal[0]},{goal[1]}&waypoints={waypoints}&option={option}"

    client_id = CFG.naver_api_id
    client_secret = CFG.naver_api_client_secret
    
    request = urllib.request.Request(url)
    request.add_header('X-NCP-APIGW-API-KEY-ID', client_id)
    request.add_header('X-NCP-APIGW-API-KEY', client_secret)
    
    response = urllib.request.urlopen(request)
    rescode = response.getcode()
    
    if (rescode == 200):
        response_body = response.read().decode('utf-8')
        route = json.loads(response_body)

        paths = route['route']['traoptimal'][0]['path']

        # due to token limit, only left 5 path points including start & end
        # only left 5 path points including start & end
        paths = paths[::len(paths)//5] + [paths[-1]]
        route['route']['traoptimal'][0]['path'] = paths

        del route['route']['traoptimal'][0]['summary']
        del route['route']['traoptimal'][0]['section']
        del route['route']['traoptimal'][0]['guide']

        return route
    else:
        return f'start: {start} goal: {goal}, waypoints: {waypoints}, Error Code: {rescode}'
