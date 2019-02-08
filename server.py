# encoding: utf8

from flask import Flask
from flask import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from parse import *
from functools import wraps
from flask import request
import re

app = Flask(__name__)

from werkzeug.contrib.cache import SimpleCache
cache = SimpleCache()

# URL templates fuer den Scraper
URL_TEMPLATES = {
    "station_details": "/haltestellen/overview/{station_id:d}/",
    "line_details": "/haltestellen/showline/{station_id:d}/{line_id:d}/",
    "schedule_table": "/haltestellen/aushang/{station_id:d}/",
    "schedule_pocket": "/haltestellen/miniplan/{station_id:d}/",
    "departures": "/qr/{station_id:d}/"
}

# Die brauchen wir bei jeder Anfrage
HEADERS = {
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/34.0.1847.137 Safari/537.36"
}

def cached(timeout=5 * 60, key='view/%s'):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            cache_key = key % request.path
            rv = cache.get(cache_key)
            if rv is not None:
                return rv
            rv = f(*args, **kwargs)
            cache.set(cache_key, rv, timeout=timeout)
            return rv
        return decorated_function
    return decorator


def get_stations():
    """
    Ruft Liste aller Stationen ab und gibt
    Dict mit ID als Schlüssel und Name als Wert aus.
    """
    url = "https://www.kvb.koeln/haltestellen/overview/"
    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text)
    #print(soup.prettify())
    mystations = []
    for a in soup.find_all("a"):
        #print(a, a.get("href"), a.text)
        href = a.get("href")
        if href is None:
            continue
        result = parse(
            URL_TEMPLATES["station_details"],
            href)
        if result is None:
            continue
        mystations.append({
            "id": int(result["station_id"]),
            "name": a.text
            })
    # sort by id
    mystations = sorted(mystations, key=lambda k: k['id'])
    station_dict = {}
    for s in mystations:
        station_dict[s["id"]] = s["name"]
    return station_dict


def get_station_details(station_id):
    """
    Liest Details zu einer Station.
    """
    url = "https://www.kvb.koeln/haltestellen/overview/%d/" % station_id
    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text)
    details = {
        "station_id": station_id,
        "name": stations[station_id],
        "line_ids": set()
    }
    div = soup.find("ul", class_="info-list")
    for a in div.find_all("a"):
        href = a.get("href")
        if href is None:
            continue
        result = parse(
            URL_TEMPLATES["line_details"],
            href)
        if result is None:
            continue
        details["line_ids"].add(result["line_id"])
    details["line_ids"] = sorted(list(details["line_ids"]))
    return details


def get_line_details(station_id, line_id):
    """
    Findet heraus, welche Stationen eine Linie anfährt
    """
    url = "https://www.kvb.koeln/haltestellen/showline/%d/%d/" % (
        station_id, line_id)
    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text)
    details = {
        "station_id": station_id,
        "line_id": line_id,
        "stations_forward": [],
        "stations_reverse": []
    }
    station_key = "stations_forward"
    count = 0
    for td in soup.find_all("td", class_=re.compile(".*station")):
        tdclass = td.get("class")[0]
        if tdclass == u'station-top':
            count = count + 1
            if count == 2:
                station_key = "stations_reverse"

        a = td.find("a")
        if a is None:
            continue
        href = a.get("href")
        if href is None:
            continue
        result = parse(
            URL_TEMPLATES["station_details"],
            href)
        if result is None:
            continue
        details[station_key].append(int(result["station_id"]))
    return details


def get_departures(station_id):
    """
    Aktuelle Abfahrten von einer Station laden
    """
    url = "https://www.kvb.koeln/qr/%d/" % station_id
    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text)
    tables = soup.find_all("table", class_="display")
    departures = []
    for row in tables[0].find_all("tr"):
        tds = row.find_all("td")
        (line_id, direction, time) = (tds[0].text, tds[1].text, tds[2].text)
        line_id = line_id.replace(u"\xa0", "")
        direction = direction.replace(u"\xa0", "")
        time = time.replace(u"\xa0", " ").strip().lower()
        if time == "sofort":
            time = "0"
        time = time.replace(" min", "")
        try:
            line_id = int(line_id)
        except:
            pass
        print(line_id, direction, time)
        departures.append({
            "line_id": line_id,
            "direction": direction,
            "wait_time": time
        })
    return departures


@app.route("/")
def index():
    output = {
        "datetime": datetime.utcnow(),
        "methods": {
            "station_list": "/stations/",
            "station_details": "/stations/{station_id}/",
            "departures": "/stations/{station_id}/departures/",
            "line_details": "/stations/{station_id}/lines/{line_id}/"
        }
    }
    return json.dumps(output)


@app.route("/stations/")
@cached()
def stations_list():
    return json.dumps(stations)


@app.route("/stations/<int:station_id>/")
@cached()
def station_details(station_id):
    details = get_station_details(station_id)
    return json.dumps(details)


@app.route("/stations/<int:station_id>/lines/<int:line_id>/")
@cached()
def line_stations(station_id, line_id):
    details = get_line_details(station_id, line_id)
    return json.dumps(details)


@app.route("/stations/<int:station_id>/departures/")
def station_departuress(station_id):
    details = get_departures(station_id)
    return json.dumps(details)

# Add CORS header to every request
@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin','*')
    resp.headers['Access-Control-Allow-Credentials'] = 'true'
    resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS, GET'
    resp.headers['Access-Control-Allow-Headers'] = request.headers.get('Access-Control-Request-Headers', 'Authorization' )
    if app.debug:
        resp.headers['Access-Control-Max-Age'] = '1'
    return resp

if __name__ == "__main__":
    stations = get_stations()
    stations_reverse = {}
    for sid in stations.keys():
        stations_reverse[stations[sid]] = sid
    app.config["DEBUG"] = True
    app.run()
