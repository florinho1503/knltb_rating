from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
import matplotlib.pyplot as plt

nr = input('wie zou je willen opzoeken?: plak het bondsnummer hier: ')
inp = int(input('\nsingles or doubles? press 1 for singles, 2 for doubles: '))

webdriver_path = "chromedriver-mac-arm64/chromedriver"

service = Service(webdriver_path)
driver = webdriver.Chrome(service=service)

wait = WebDriverWait(driver, 10)

url = "https://mijnknltb.toernooi.nl/player-profile/34b4ec17-e82a-425c-8e33-8b79e4dbf5ff/Rating"
driver.get(url)

data = []

def playerLookup(nr):

    search_toggle_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'label[for="MastheadSearchInput"]'))
    )

    search_toggle_button.click()

    search_input = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, 'MastheadSearchInput'))
    )
    search_input.send_keys(nr)
    time.sleep(5)

    player_link = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "a.nav-link.media__link"))
    )

    driver.execute_script("arguments[0].setAttribute('href', arguments[0].getAttribute('href') + '/rating');",
                          player_link)

    player_link.click()


def handleCookies():
    settings_button = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, 'js-show-purposes')))
    settings_button.click()

    wait.until(EC.visibility_of_element_located((By.ID, 'form-purposes')))

    select_all_button = driver.find_element(By.CLASS_NAME, 'js-select-all-save')
    select_all_button.click()

    wait.until(EC.staleness_of(select_all_button))


def MoreDetails(input):
    more_details_buttons = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'button.btn--more-details')))

    if input == 1:
        more_details_buttons[0].click()
    elif input == 2:
        more_details_buttons[1].click()



def getPageContent():
    time.sleep(5)
    html_content = driver.page_source

    soup = BeautifulSoup(html_content, 'html.parser')

    return soup


def scrapeYear(soup, player_name):
    date_pattern = re.compile(r'\b\d{1,2}-\d{1,2}-\d{4}\b')
    matches = soup.find_all('li', class_='match-group__item')

    for match in matches:
        players = match.find_all('span', class_='nav-link__value')
        player_in_match = any(player_name in player.text for player in players)

        if player_in_match:
            rating_tag = match.find('a', class_='nav-link', text=player_name).find_next_sibling('span',
                                                                                                  class_='match__row-title-aside')
            if rating_tag:
                rating = rating_tag.get_text(strip=True).strip('()')
            else:
                continue

            date_text = match.find('li', class_='match__footer-list-item').find('span', class_='nav-link__value')
            if date_text:
                date_matches = date_pattern.findall(date_text.get_text())
                if date_matches:
                    date = date_matches[0]
                else:
                    continue
            else:
                continue
            data.append({'date': date, 'rating': rating})

    for result in data:
        print(f"Date: {result['date']}, Rating: {result['rating']}")

    if data:
        best_rating = min(data, key=lambda x: x['rating'])
        return best_rating
    else:
        print("No valid data found")
        return 10


def otherYears():
    list_items = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'ul.page-nav--pills li')))

    non_active_list_items = [li for li in list_items if "page-nav__item--active" not in li.get_attribute("class")]

    return non_active_list_items[:2]


def Quit():
    driver.quit()


def switchTab(year):
    tab_link = year.find_element(By.TAG_NAME, 'a')
    print(f"\n\nClicking on tab: {tab_link.text}")

    tab_link.click()

    time.sleep(2)


def plotGraph(data, player_name):
    dates = [datetime.strptime(entry["date"], "%d-%m-%Y") for entry in data]
    ratings = [float(entry["rating"].replace(",", ".")) for entry in data]
    plt.figure(figsize=(10, 6))
    plt.plot(dates, ratings, marker='o', linestyle='-', color='b')
    plt.xlabel("Date")
    plt.ylabel("Rating")
    plt.title(f"Player Rating Over Time for {player_name}")
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()


def main(name):
    handleCookies()
    playerLookup(name)
    MoreDetails(inp)
    soup = getPageContent()
    media_snippet = soup.find('div', class_='media')
    player_name = media_snippet.find('span', class_='nav-link__value').text
    print(f'Data verzamelen voor {player_name}... \n')
    best_rating = scrapeYear(soup, player_name)
    other_years = otherYears()
    for year in other_years:
        switchTab(year)
        MoreDetails(inp)
        soup = getPageContent()
        best_rating = scrapeYear(soup, player_name)

    print(f"Best Rating: {best_rating['rating']} on Date: {best_rating['date']}")
    plotGraph(data, player_name)

    Quit()


main(nr)
