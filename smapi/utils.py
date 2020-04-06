import httpx
import re

# from .core import headers

headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:72.0) Gecko/20100101 Firefox/72.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Encoding': 'gzip,deflate,sdch',
    'Accept-Language': 'en-US,en;q=0.8',
    # 'Accept-Charset': 'utf-8, iso-8859-1, utf-16, *;q=0.1',
    # 'Connection': 'keep-alive',
    # 'Keep-Alive': '300',
    'DNT': '1',
}


# TODO: class to get one r object etc.


def freeIds():
    """Returns currently live promotions - list of app_ids."""
    # TODO: ability to return weekend only
    # https://steamdb.info/sales/?min_discount=0&min_rating=0&cc=ua&category=29  + price filter
    r = httpx.Client(headers=headers)
    rc = r.get('https://steamdb.info/upcoming/free/').text
    rc = rc[:rc.find('<a href="#upcoming-promotions">Upcoming promotions</a>')]  # cut upcoming, we need only live
    app_ids = [int(i[0]) for i in re.findall(r'<img src=".+?/([0-9]+)/.+>\n</a>\n</td>\n<td>\n<a href="/sub/([0-9]+)/">\n<b>(.+)</b>', rc) if 'weekend' not in i[2].lower()]  # ugly pattern
    return app_ids


def freeFreeIds():
    r = httpx.Client(headers=headers)
    rc = r.get('https://steamdb.info/freepackages/').text
    regex_pattern = r'data-subid="([0-9]+)" data-appid="([0-9]+)" data-parent="[\-0-9]+">		<a href="/sub/[0-9]+/">[0-9]+</a>, // <button class="remove btn btn-link">\[REMOVE\]</button> (.+?(?<![Demo|demo|Trailer]))\n'
    apps = [{'sub_id': int(i[0]), 'app_id': int(i[1]), 'name': i[2]} for i in re.findall(regex_pattern, rc) if ' trailer' not in i[2].lower() and ' demo' not in i[2].lower()]
    return apps
