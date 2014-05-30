# encoding: utf8

from flask import Flask
from flask import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from parse import *
from functools import wraps
from flask import request

app = Flask(__name__)

from werkzeug.contrib.cache import SimpleCache
cache = SimpleCache()

# URL templates fuer den Scraper
URL_TEMPLATES = {
    "station_details": "/german/hst/overview/{station_id:d}/",
    "line_details": "/german/hst/showline/{station_id:d}/{line_id:d}/",
    "schedule_table": "/german/hst/aushang/{station_id:d}/",
    "schedule_pocket": "/german/hst/miniplan/{station_id:d}/",
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
    url = "http://www.kvb-koeln.de/german/hst/overview/"
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


@app.route("/")
def index():
    output = {
        "datetime": datetime.utcnow(),
        "methods": {
            "station_list": "/stations/",
            "station_details": "/stations/{id}",
            "line_details": "/lines/{id}"
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
    url = "http://www.kvb-koeln.de/german/hst/overview/%d/" % station_id
    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text)
    details = {
        "station_id": station_id,
        "name": stations[station_id],
        "line_ids": set()
    }
    div = soup.find("div", class_="fliesstext")
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
    return json.dumps(details)


if __name__ == "__main__":
    stations = get_stations()
    app.config["DEBUG"] = True
    app.run()
