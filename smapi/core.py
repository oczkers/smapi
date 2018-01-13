import requests
import re
import urllib.parse
import time
import random
from bs4 import BeautifulSoup
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


def orders():  # TODO: login required to work of course
    orders = {'buy': [],
              'sell': []}
    # sell orders
    start = 0
    count = 100
    while True:
        params = {'query': '',
                  'start': start,
                  'count': count}
        rc = r.get('https://steamcommunity.com/market/mylistings/render/?query=&start=10&count=10', params=params).json()
        for game_id in rc['assets']:
            for context_id in game_id:
                for order in context_id:
                    orders['sell'].append({'game_id': order['appid'],
                                           'order_id': order['id'],
                                           'amount': order['amount'],
                                           'original_amount': order['original_amount'],
                                           'status': order['status'],  # 2 active listing
                                           'item_name': order['name'],  # market_name  market_hash_name
                                           'commodity': order['commodity'], })
                    # TODO: price in order['hovers']
        if len() < count:  # use total_count / num_active_listings instead?
            break
        start += count

    # buy orders
    rc = r.get('https://steamcommunity.com/market/').text
    bs = BeautifulSoup(rc)
    divs = bs.findAll('div', {'class': 'market_listing_row market_recent_listing_row'})
    for div in divs:
        order_id = int(div.attrs['id'].replace('mybuyorder_', ''))
        game_name = div.find('span', {'class': 'market_listing_game_name'}).text
        # item_name = div.find('span', {'class': 'market_listing_item_name'}).a.text
        game_id, item_name = div.find('span', {'class': 'market_listing_item_name'}).a.attrs['href'].split('/')[-2:]
        item_id, item_name = re.search('([0-9]+\-)?(.+)', item_name).groups()
        # amount = div.span()[0].span.text.replace(' @', '')
        # amount = div.find('span', {'class': 'market_listing_inline_buyorder_qty'}).text.replace(' @', '')
        amount, price = list(div.find('span', {'class': 'market_listing_price'}).strings)[1:]
        amount = amount.replace(' @', '')
        price = price.strip()  # remove currency code
        orders['buy'].append({'order_id': order_id,
                              'game_id': game_id,
                              'game_name': game_name,
                              'item_id': item_id,
                              'item_name': item_name,
                              'amount': amount,
                              'price': price, })
    return orders
