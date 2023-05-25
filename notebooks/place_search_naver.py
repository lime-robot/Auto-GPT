import os
import json
import copy
import time
import concurrent.futures
from tqdm import tqdm

import tiktoken
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

load_dotenv('.env')
openai.api_key = os.environ.get("OPENAI_API_KEY")


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

def get_selenium_driver():
    chromium_driver_path = Path("/usr/bin/chromedriver")
    options = webdriver.ChromeOptions()
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.5615.49 Safari/537.36"
    )
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(
        executable_path=chromium_driver_path
        if chromium_driver_path.exists()
        else ChromeDriverManager().install(),
        options=options,
    )
    return driver

def summarize_reviews(reviews, query):
    message = create_message("\n".join(reviews), query)
    response = get_chatgpt_response([message], model='gpt-3.5-turbo', temperature=0)['content']
    return response

def get_reviews(soup, query):
    sections = soup.find_all('div', class_='place_section')
    review_section = None
    for section in sections:
        header = section.find(class_='place_section_header')
        if header and header.find(string=True, recursive=False) == '리뷰':
            review_section = section
            break
    if review_section:
        reviews = []
        li_elements = review_section.find('div', {'class': 'place_section_content'}).find('ul').find_all('li')
        for li in li_elements[:5]:
            review_text_element = li.find('a', class_='xHaT3').find('span')
            if review_text_element:  # 'span' 태그가 존재하면
                review = review_text_element.get_text(strip=True)
                reviews.append(review)
        if len(reviews) > 0:            
            reviews = summarize_reviews(reviews, query)
            return reviews

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

def get_place_details(place_url, query):
    print(f'BROWSING: {place_url}')
    driver = get_selenium_driver()
    details = {
        'url': place_url,
        'name': None,
        'description': None,
        'rating': None,
        'n_visitor_reviews': None,
        'n_blog_reviews': None,
        'reviews': None,
    }
    
    driver.get(place_url)
    time.sleep(1)
    place_type = driver.current_url.split('/')[3]
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    # name / description
    spans = soup.find('div', {'id': '_title'}).find_all('span')
    details['name'] = spans[0].text
    if len(spans) > 1:
        details['description'] = spans[1].text
    # ratings
    for span in soup.find('div', {'class': 'place_section'}).find_all('span'):
        text = span.text
        if text.startswith('별점') and (span.find('em') is not None):
            details['rating'] = text.replace('별점', '').strip()
        if text.startswith('방문자리뷰') and (span.find('em') is not None):
            details['n_visitor_reviews'] = text.replace('방문자리뷰', '').strip()
        elif text.startswith('블로그리뷰') and (span.find('em') is not None):
            details['n_blog_reviews'] = text.replace('블로그리뷰', '').strip()
    # reviews
    driver.get(f'{place_url}/review/visitor')
    time.sleep(1)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    reviews = get_reviews(soup, query)
    details['reviews'] = reviews
    driver.quit()
    return details

def search_places(place_name, query='', max_results=8):    
    driver = get_selenium_driver()
    naver_map_search_url = f'https://m.map.naver.com/search2/search.naver?query={place_name}'
    driver.get(naver_map_search_url)
    time.sleep(2)
    elements = driver.find_elements_by_css_selector('li._item._lazyImgContainer')[:max_results]
    if len(elements) == 0:
        driver.quit()
        return []
    def get_place_details_(place_url):
        return get_place_details(place_url, query=query)
    with concurrent.futures.ThreadPoolExecutor(len(elements)) as executor:
        results = list(executor.map(get_place_details_, [(f"https://m.place.naver.com/place/{element.get_attribute('data-id')}") for element in elements]))    
    #results = []
    for i in range(len(elements)):
        #place_url = f"https://m.place.naver.com/place/{element.get_attribute('data-id')}"
        #place_details = get_place_details(place_url, query)
        results[i]['longitude'] = float(elements[i].get_attribute('data-longitude'))
        results[i]['latitude'] = float(elements[i].get_attribute('data-latitude'))
        
    driver.quit()
    
    num_places = len(results)
    distances = np.zeros((num_places, num_places))
    for i in range(num_places):
        for j in range(num_places):
            loc_i = (results[i]['latitude'], results[i]['longitude'])
            loc_j = (results[j]['latitude'], results[j]['longitude'])
            distances[i, j] = haversine(loc_i, loc_j)

    for result in results:
        del result['longitude'], result['latitude']
    
    distances_str = np.array2string(distances, precision=1, floatmode='fixed')
    return json.dumps({"candidates": results, "distance_matrix": distances_str}, ensure_ascii=False)


if __name__ == '__main__':
    #get_latitude_longitude('1546882334')
    results = search_places('광교호수공원 맛집', query='')
    
    print(results)