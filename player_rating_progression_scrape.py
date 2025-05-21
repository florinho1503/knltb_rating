from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
from datetime import date
import json
from pathlib import Path
import sqlite3
import matplotlib.pyplot as plt
from analysis import generate_rating_plot_html


def playerLookup(nr, driver):

    search_toggle_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'label[for="MastheadSearchInput"]'))
    )

    search_toggle_button.click()

    search_input = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, 'MastheadSearchInput'))
    )
    search_input.send_keys(nr)

    player_link = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "a.nav-link.media__link"))
    )

    driver.execute_script("arguments[0].setAttribute('href', arguments[0].getAttribute('href') + '/rating');",
                          player_link)

    player_link.click()


def handleCookies(wait, driver):
    settings_button = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, 'js-show-purposes')))
    settings_button.click()

    wait.until(EC.visibility_of_element_located((By.ID, 'form-purposes')))

    select_all_button = driver.find_element(By.CLASS_NAME, 'js-select-all-save')
    select_all_button.click()

    wait.until(EC.staleness_of(select_all_button))


def MoreDetails(input, wait):
    more_details_buttons = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'button.btn--more-details')))

    if input == 1:
        more_details_buttons[0].click()
    elif input == 2:
        more_details_buttons[1].click()



def getPageContent(driver):
    time.sleep(5)
    html_content = driver.page_source

    soup = BeautifulSoup(html_content, 'html.parser')

    return soup


def insertDB(soup, c, conn):
    matches = soup.find_all('li', class_='match-group__item')

    for item in matches:
        # 3a. Check for scores: if empty, skip (match not played)
        point_lists = item.select('.match__result .points')
        if not point_lists:
            continue

        # 3b. Parse players + ratings
        def parse_player(span):
            name = span.find('span', class_='nav-link__value').get_text(strip=True)
            m = re.search(r'\(([\d,\.]+)\)', span.get_text())
            rating = float(m.group(1).replace(',', '.')) if m else None
            return name, rating

        rows = item.select('.match__row-title-value-content')
        p1, r1 = parse_player(rows[0])
        p2, r2 = parse_player(rows[1])

        # 3c. Parse sets (now up to 3)
        scores = []
        for ul in point_lists:
            nums = [int(li.get_text(strip=True)) for li in ul.select('.points__cell')]
            scores.append(nums)
        # pad to 3 sets
        while len(scores) < 3:
            scores.append([None, None])
        (set1_p1, set1_p2), (set2_p1, set2_p2), (set3_p1, set3_p2) = scores

        # 3d. Determine winner
        win_span = item.select_one('.match__row.has-won .nav-link__value')
        winner = win_span.get_text(strip=True) if win_span else None

        # 3e. Parse date
        date_elem = item.select_one('.match__footer .icon-clock + .nav-link__value')
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            # strip off weekday (“za 10-5-2025” → “10-5-2025”)
            date_part = date_text.split(' ', 1)[1]
            match_date = datetime.strptime(date_part, '%d-%m-%Y').date()
        else:
            match_date = None

        dup = c.execute('''
                    SELECT 1 FROM matches
                     WHERE player1 = ?
                       AND player2 = ?
                       AND set1_p1 = ? AND set1_p2 = ?
                       AND set2_p1 = ? AND set2_p2 = ?
                       AND set3_p1 = ? AND set3_p2 = ?
                ''', (
            p1, p2,
            set1_p1, set1_p2,
            set2_p1, set2_p2,
            set3_p1, set3_p2
        )).fetchone()
        if dup:
            continue

        # --- 4. Insert into DB ---
        c.execute('''
                    INSERT INTO matches
                    (player1, rating1, player2, rating2,
                     set1_p1, set1_p2, set2_p1, set2_p2,
                     set3_p1, set3_p2,
                     winner, match_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (p1, r1, p2, r2,
                      set1_p1, set1_p2, set2_p1, set2_p2,
                      set3_p1, set3_p2,
                      winner, match_date))
        conn.commit()


def otherYears(wait):
    list_items = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'ul.page-nav--pills li')))

    non_active_list_items = [li for li in list_items if "page-nav__item--active" not in li.get_attribute("class")]
    non_active_list_items = non_active_list_items[:3]

    return non_active_list_items[:2]

def toggle(wait):
    more_li = wait.until(EC.presence_of_element_located((
        By.CSS_SELECTOR,
        "ul.page-nav--pills li.page-nav__item--more:not(.is-hidden)"
    )))

    # 2️⃣ Click its toggle <span>
    toggle = more_li.find_element(By.CSS_SELECTOR, "span.js-toggle-dropdown")
    toggle.click()

def MoreYears(wait):
    more_li = wait.until(EC.presence_of_element_located((
        By.CSS_SELECTOR,
        "ul.page-nav--pills li.page-nav__item--more:not(.is-hidden)"
    )))

    # 2️⃣ Click its toggle <span>
    toggle = more_li.find_element(By.CSS_SELECTOR, "span.js-toggle-dropdown")
    toggle.click()

    #  (optionally wait a tiny bit for any animation)
    time.sleep(0.5)

    # 3️⃣ Now, from that same <li>, find its dropdown-items
    dropdown_items = more_li.find_elements(
        By.CSS_SELECTOR,
        "ul.page-nav--more li.js-page-nav__item.page-nav__item"
    )

    return dropdown_items[:5]

def Quit(driver):
    driver.quit()


def switchTab(year):
    tab_link = year.find_element(By.TAG_NAME, 'a')

    tab_link.click()

    time.sleep(2)

def currentRating(soup, inp):
    ratings = soup.find_all("span", class_="tag-duo__value")
    if inp == 1:
        rating = ratings[0].text
    else:
        rating = ratings[1].text
    return rating

def main(name):
    inp = 1
    max_years = 8

    webdriver_path = "chromedriver-mac-arm64/chromedriver"

    service = Service(webdriver_path)
    driver = webdriver.Chrome(service=service)

    wait = WebDriverWait(driver, 10)

    url = "https://mijnknltb.toernooi.nl/player-profile/34b4ec17-e82a-425c-8e33-8b79e4dbf5ff/Rating"
    driver.get(url)

    data = []

    conn = sqlite3.connect('matches.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY,
            player1 TEXT,
            rating1 REAL,
            player2 TEXT,
            rating2 REAL,
            set1_p1 INTEGER,
            set1_p2 INTEGER,
            set2_p1 INTEGER,
            set2_p2 INTEGER,
            set3_p1 INTEGER,
            set3_p2 INTEGER,
            winner TEXT,
            match_date DATE
        )
        ''')
    conn.commit()

    c.execute('''
        CREATE TABLE IF NOT EXISTS current_ratings (
            name   TEXT,
            rating REAL,
            date   DATE
        )
        ''')
    conn.commit()
    handleCookies(wait, driver)
    # 1. wait for the consent iframe to appear
    consent_iframe = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((
            By.CSS_SELECTOR,
            "iframe[src*='consentui']"
        ))
    )
    # 2. switch into it
    driver.switch_to.frame(consent_iframe)

    # 3. locate & click the “Accept and continue” div inside that frame
    btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((
            By.XPATH,
            "//div[@id='buttons']//div[contains(@class,'btn') and contains(@class,'green')]"
        ))
    )
    btn.click()

    # 4. switch back to the main page
    driver.switch_to.default_content()

    # for name in [28690818, 30209986, 31348750, 28655087, 30502160, 28244672, 27329429]:

    playerLookup(name, driver)
    MoreDetails(inp, wait)
    soup = getPageContent(driver)
    media_snippet = soup.find('div', class_='media')
    player_name = media_snippet.find('span', class_='nav-link__value').text
    print(f'Data verzamelen voor {player_name}... \n')
    current_rating = currentRating(soup, inp)
    today_str = date.today().strftime("%Y-%m-%d")
    data.append({'date': today_str, 'rating': current_rating})

    rating_val = float(current_rating.replace(',', '.'))
    c.execute('''
            INSERT INTO current_ratings (name, rating, date)
            VALUES (?, ?, ?)
        ''', (player_name, rating_val, today_str))
    conn.commit()

    insertDB(soup, c, conn)
    other_years = otherYears(wait)
    years = 1

    for year in other_years:
        if years > max_years:
            break
        switchTab(year)
        MoreDetails(inp, wait)
        soup = getPageContent(driver)
        insertDB(soup, c, conn)
        years+= 1

    extra_years = MoreYears(wait)
    toggle(wait)
    for year in extra_years:
        if years > max_years:
            break
        toggle(wait)
        switchTab(year)
        MoreDetails(inp, wait)
        soup = getPageContent(driver)
        insertDB(soup, c, conn)
        years+=1

    conn.close()
    Quit(driver)
