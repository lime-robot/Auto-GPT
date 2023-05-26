import requests
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor
from autogpt.commands.map import *
from pprint import pprint

if __name__ == "__main__":
    # place_url = "https://place.map.kakao.com/469577034"
    # print(get_kakao_review(place_url))

    # place_url = "https://place.map.kakao.com/2011092566"
    # print(get_kakao_review(place_url))

    # place_url = "https://place.map.kakao.com/469577034"
    # print(get_place_info(place_url))

    # place_url = "https://place.map.kakao.com/2011092566"
    # print(get_place_info(place_url))

    # pprint(search_place_from_keyword_using_kakaoAPI("서울역 맛집", "FD6"))

    write_markdown_report_from_files(
        [
            "/Users/ynot/Workspace/askup/Auto-GPT-limerobot/autogpt/auto_gpt_workspace/gangneung_attractions.txt",
            "/Users/ynot/Workspace/askup/Auto-GPT-limerobot/autogpt/auto_gpt_workspace/gangneung_restaurants.txt",
        ],
        "Sokcho One-Day Trip Itinerary",
        "Include links and images",
        "sokcho_trip_report.md"
        )
