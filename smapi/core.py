import requests
import re
import urllib.parse
import time
import random
# from clint.textui import colored

headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.84 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Encoding': 'gzip,deflate,sdch',
    'Accept-Language': 'en-US,en;q=0.8',
    # 'Accept-Charset': 'utf-8, iso-8859-1, utf-16, *;q=0.1',
    # 'Connection': 'keep-alive',
    # 'Keep-Alive': '300',
    'DNT': '1',
}

r = requests.Session()
r.headers = headers


def price(id, name):
    time.sleep(random.randint(15, 25))
    # get item_nameid (this can be skipped when item_nameid is in database)
    # encode name?
    if name == 'MajorMinor':  # fix database
        name = 'Major-Minor'
    name = urllib.parse.quote('%s Booster Pack' % name)
    url = 'https://steamcommunity.com/market/listings/753/%s-%s' % (id, name)
    print(url)
    rc = r.get(url).text  # 753 = (normal?) booster pack
    open('log.log', 'w').write(rc)
    if "You've made too many requests recently. Please wait and try your request again later." in rc:
        print("You've made too many requests recently. Please wait and try your request again later.")
        asd
    item_nameid = re.search('Market_LoadOrderSpread\( ([0-9]+) \);', rc).group(1)

    # get price
    params = {'country': 'PL',
              'language': 'english',
              'currency': 6,  # 6 PLN, 3 EUR
              'item_nameid': item_nameid,
              'two_factor': 0}
    rc = r.get('https://steamcommunity.com/market/itemordershistogram', params=params).json()
    # if rc['lowest_sell_order'] is None:
    #     return None
    if rc['highest_buy_order'] is None:
        return 0
    # return int(rc['lowest_sell_order'])
    return int(rc['highest_buy_order'])
