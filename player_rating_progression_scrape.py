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
import matplotlib.pyplot as plt

nr = input('wie zou je willen opzoeken?: plak het bondsnummer hier: ')
# nr = '26473402'
inp = int(input('\nsingles or doubles? press 1 for singles, 2 for doubles: '))
# inp = 1
max_years = int(input('\nHow many years ago do you want to look back (max=8): '))

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
    non_active_list_items = non_active_list_items[:3]

    return non_active_list_items[:2]

def toggle():
    more_li = wait.until(EC.presence_of_element_located((
        By.CSS_SELECTOR,
        "ul.page-nav--pills li.page-nav__item--more:not(.is-hidden)"
    )))

    # 2️⃣ Click its toggle <span>
    toggle = more_li.find_element(By.CSS_SELECTOR, "span.js-toggle-dropdown")
    toggle.click()

def MoreYears():
    more_li = wait.until(EC.presence_of_element_located((
        By.CSS_SELECTOR,
        "ul.page-nav--pills li.page-nav__item--more:not(.is-hidden)"
    )))
    print("DEBUG: Found the visible <li>:", more_li.get_attribute("outerHTML")[:100], "…")

    # 2️⃣ Click its toggle <span>
    toggle = more_li.find_element(By.CSS_SELECTOR, "span.js-toggle-dropdown")
    toggle.click()
    print("DEBUG: Clicked the toggle span")

    #  (optionally wait a tiny bit for any animation)
    time.sleep(0.2)

    # 3️⃣ Now, from that same <li>, find its dropdown-items
    dropdown_items = more_li.find_elements(
        By.CSS_SELECTOR,
        "ul.page-nav--more li.js-page-nav__item.page-nav__item"
    )

    return dropdown_items[:5]

def Quit():
    driver.quit()


def switchTab(year):
    tab_link = year.find_element(By.TAG_NAME, 'a')
    print(f"\n\nClicking on tab: {tab_link.text}")

    tab_link.click()

    time.sleep(2)

def currentRating(soup, inp):
    ratings = soup.find_all("span", class_="tag-duo__value")
    if inp == 1:
        rating = ratings[0].text
    else:
        rating = ratings[1].text
    return rating


def generate_rating_plot_html(dates, ratings, player_name, output_path="rating_plot.html"):
    """
    dates     : list of ISO-strings, e.g. ["2022-05-10", "2022-05-17", …]
    ratings   : list of floats,      e.g. [6.01, 6.05, …]
    player_name: string
    output_path: filename to write
    """
    iso_dates = [
        datetime.strptime(entry["date"], "%d-%m-%Y").strftime("%Y-%m-%d")
        for entry in data
    ]
    ratings_js = json.dumps(
        [float(entry["rating"].replace(",", ".")) for entry in data]
    )
    dates_js = json.dumps(iso_dates)
    player_js = json.dumps(player_name)


    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Player Rating Over Time</title>
  <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; background: #f4f4f9; margin:0; }}
    .container {{
      max-width:960px; margin:40px auto;
      background:#fff; border-radius:8px;
      box-shadow:0 2px 8px rgba(0,0,0,0.1);
      padding:20px;
    }}
    h1 {{ text-align:center; color:#333; margin-bottom:0.5em; }}
    #chart {{ width:100%; height:500px; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Player Rating Over Time for <span id="playerName"></span></h1>
    <div id="chart"></div>
  </div>
  <script>
    const dates   = {dates_js};
    const ratings = {ratings_js};
    const playerName = {player_js};

    document.getElementById('playerName').textContent = playerName;
    
    const yMin = Math.min(...ratings) - 0.2;
    const yMax = Math.max(...ratings) + 0.2;


    const trace = {{
      x: dates,
      y: ratings,
      mode: 'lines+markers',
      type: 'scatter',
      marker: {{ size: 8, color: '#0074D9' }},
      line: {{ shape: 'spline', smoothing: 0.5, color: '#0074D9' }},
      hovertemplate: '%{{x}}<br>Rating: %{{y}}<extra></extra>'
    }};
    
    const bestValue = Math.min(...ratings);
    const bestIndex = ratings.indexOf(bestValue);
    const bestDate  = dates[bestIndex];
    const traceBest = {{
      x: [bestDate],
      y: [bestValue],
      mode: 'markers+text',
      type: 'scatter',
      marker: {{ size: 12, color: '#FF4136' }},
      text: ['Best'],
      textposition: 'top center',
      hovertemplate: 'Best: %{{y}} on %{{x}}<extra></extra>'
    }};

    const layout = {{
      margin:{{l:60,r:40,t:60,b:60}},
      xaxis:{{ title:'Date', type:'date', tickformat:'%Y-%m-%d', tickangle:-45 }},
      yaxis:{{ title:'Rating', range:[yMin, yMax] }},
      plot_bgcolor:'#fafafa',
      paper_bgcolor:'#ffffff',
      hovermode:'closest'
    }};

    Plotly.newPlot('chart', [trace, traceBest], layout, {{responsive: true}});
  </script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Wrote interactive chart to {output_path}")



def main(name):
    handleCookies()
    time.sleep(10)
    playerLookup(name)
    MoreDetails(inp)
    soup = getPageContent()
    media_snippet = soup.find('div', class_='media')
    player_name = media_snippet.find('span', class_='nav-link__value').text
    print(f'Data verzamelen voor {player_name}... \n')
    current_rating = currentRating(soup, inp)
    data.append({'date': date.today().strftime("%d-%m-%Y"), 'rating': current_rating})

    best_rating = scrapeYear(soup, player_name)
    other_years = otherYears()
    years = 1

    for year in other_years:
        if years > max_years:
            break
        switchTab(year)
        MoreDetails(inp)
        soup = getPageContent()
        best_rating = scrapeYear(soup, player_name)
        years+= 1

    extra_years = MoreYears()
    toggle()
    for year in extra_years:
        if years > max_years:
            break
        toggle()
        switchTab(year)
        MoreDetails(inp)
        soup = getPageContent()
        best_rating = scrapeYear(soup, player_name)
        years+=1

    print(f"Best Rating: {best_rating['rating']} on Date: {best_rating['date']}")
    dates = [entry["date"] for entry in data]
    ratings = [float(entry["rating"].replace(",", ".")) for entry in data]

    # 2. Call our HTML generator
    generate_rating_plot_html(
        dates,
        ratings,
        player_name=player_name,  # or whatever your variable is
        output_path=f"{player_name}.html"
    )

    Quit()


main(nr)
