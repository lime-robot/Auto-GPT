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

def get_place_info(place_url):
    options = webdriver.ChromeOptions()
    options.add_argument('headless')

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), 
        options=options
    )

    driver.get(place_url)

    try:
        rating = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR, 
                '#mArticle > div.cont_essential > div:nth-child(1) > div.place_details > div > div > a:nth-child(3) > span.color_b'
            ))
        ).text
    except:
        rating = "-1"

    try:
        num_review = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR, 
                    '#mArticle > div.cont_essential > div:nth-child(1) > div.place_details > div > div > a:nth-child(3) > span.color_g'
                ))
            ).text
        num_review = re.findall(r'\d+', num_review)[0]
    except:
        num_review = "-1"

    try:
        num_blog_review = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((
                    By.CSS_SELECTOR, 
                    '#mArticle > div.cont_essential > div > div.place_details > div > div > a > span'
                ))
            ).text
    except:
        num_blog_review = "-1"

    driver.quit()

    review = get_kakao_review(place_url)

    return rating, num_review, num_blog_review, review

@command(
    "search_place_for_keyword_using_kakaoAPI_and_save_to_file",
    "Search Place For Keyword Using KakaoAPI's category_group_code And Save to File",
    '"keyword": "<keyword_reflecting_category_group_code_and_location>", "category_group_code": "<category_group_code>", "filename": "<path_to_save_the_result_as_txt>"',
)
def search_place_from_keyword_using_kakaoAPI(keyword, category_group_code=None, filename="sample.txt"):
    api_key = CFG.kakao_api_key
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    size = 2
    num_page = 1

    headers = {
        "Authorization": f"KakaoAK {api_key}"
    }
    params = {
        "query": keyword,
        "category_group_code": category_group_code,
        "size": size,
    }

    results = []
    prev_result = None
    for page in range(1, num_page+1):
        params["page"] = page
        response = requests.get(url, headers=headers, params=params)
        result = response.json()['documents']

        if len(result) == 0:
            return "There are no results. Please suggest another keyword."

        if prev_result is not None:
            if all([v1 == v2 for v1, v2 in zip([r['place_url'] for r in result], [r['place_url'] for r in prev_result])]):
                break

        with ThreadPoolExecutor(max_workers=size) as executor:
            ret = list(executor.map(get_place_info, [r['place_url'] for r in result]))
            ret = zip(*ret)

        for r, rating, num_review, num_blog_reviews, review in zip(result, *ret):
            r['rating'] = rating
            r['num_review'] = num_review
            r['num_blog_reviews'] = num_blog_reviews
            r['review'] = review

        results += result
        prev_result = result

    results = [
        {
            'place_name': r['place_name'],
            'place_url': r['place_url'],
            'rating': r['rating'],
            'num_review': r['num_review'],
            'num_blog_reviews': r['num_blog_reviews'],
            'review': r['review'],
            # 'latitude': r['x'], 
            # 'longitude': r['y'], 
        } for r in results
    ]

    with open(filename, 'w') as f:
        f.write(str(results))
    return f"Written to {filename}"

@command(
    "write_markdown_report_from_files",
    "Read files and write a high quality report in markdown format",
    '"read_filenames": "<list_of_filename_to_read_and_refer_to>", "topic": "<topic_of_the_report>", "requirements": "<requirements>", "save_filename": "<filename_to_save_the_report_to>"'
)
def write_markdown_report_from_files(read_filenames, topic, requirements, save_filename):
    print(read_filenames, save_filename)
    texts = []
    for filename in read_filenames:
        with open(filename) as f:
            texts.append(f"{Path(filename).stem}\n```\n{f.read()}\n```")
    context = "\n\n".join(texts)

    prompt = f"""
Here are references:
{context}

Here are requirements:
1. 위 정보를 고려해서 report를 작성하세요.
2. rating, num_review, num_blog_reviews, review 정보를 이용해서 적절한 장소를 3개씩 추천해주세요.
3. 장소에 대한 링크와 이미지를 포함하세요.
4. review 정보를 이용해서 추천된 장소의 장점, 단점을 item bullet 포맷으로 작성하세요.
5. 마지막으로 추천된 장소를 어떤 순서로 방문하면 좋을지 시간의 흐름에 따라 작성하세요. 한국의 아침 시간은 07시~09시, 점심시간은 11시~13시, 저녁시간은 17시~19시입니다.

Write a professional markdown report of topic "Sokcho One-Day Trip Itinerary" considering "gangneung_attractions", "gangneung_restaurants". Write down in korean.
""".strip()

    print(prompt)
    model = "gpt-3.5-turbo" # "gpt-4" # gpt-3.5-turbo
    response = create_chat_completion([{"role": "user", "content": prompt}], model=model, temperature=0.5)
    with open(save_filename, "w") as f:
        f.write(response)
    return f"Written to {Path(save_filename).stem}"
