import requests
import re
import urllib.parse
import json
import time
import random
import pyotp
import base64
import datetime
from dateutil import parser
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from bs4 import BeautifulSoup
from urllib.parse import unquote
try:
    from cookielib import LWPCookieJar
except ImportError:
    from http.cookiejar import LWPCookieJar
# from clint.textui import colored

from .exceptions import SmapiError

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

cookies_file = 'cookies.txt'


def hashPasswd(passwd, mod, exp):
    '''RSA encode password.'''
    mod = int(str(mod), 16)
    exp = int(str(exp), 16)
    rsa = RSA.construct((mod, exp))
    cipher = PKCS1_v1_5.new(rsa)
    return base64.b64encode(cipher.encrypt(passwd.encode()))


class Core(object):
    def __init__(self, username, passwd, totp=None):
        self.username = username
        self.passwd = passwd
        self.totp = totp
        self.r = requests.Session()  # init/reset requests session object
        self.r.headers = headers.copy()  # i'm chrome browser now ;-)
        self.cookies_file = cookies_file
        self.currency = 6  # 6 PLN, 3 EUR
        # load saved cookies/session
        if self.cookies_file:
            self.r.cookies = LWPCookieJar(self.cookies_file)
            try:
                self.r.cookies.load(ignore_discard=True)  # is it good idea to load discarded cookies after long time?
            except IOError:
                pass
                # self.r.cookies.save(ignore_discard=True)  # create empty file for cookies
        # encode password
        rc = self.r.get('https://steamcommunity.com/login/home/').text
        open('smapi.log', 'w').write(rc)
        if 'javascript:Logout();' not in rc:
            self.login(username, passwd)
            # TODO?: detect session_id in login
            rc = self.r.get('https://steamcommunity.com/login/home/').text
            open('smapi.log', 'w').write(rc)
        self.session_id = re.search('g_sessionID = "(.+?)";', rc).group(1)
        # rc = self.r.get('https://steamcommunity.com/id/oczun/').text
        # self.steam_id = re.search('g_steamID = "76561198011812285";', rc).group(1)

    def saveSession(self):
        '''Saves cookies/session.'''
        if self.cookies_file:
            self.r.cookies.save(ignore_discard=True)

    def login(self, username, passwd, email_code=None, auth_name=None, twofactor_code=None):
        data = {'username': username, 'donotcache': int(time.time() * 1000)}
        rc = self.r.post('https://steamcommunity.com/login/getrsakey/', data=data).json()
        if not rc['success']:
            return False
        passwd_hash = hashPasswd(passwd, rc['publickey_mod'], rc['publickey_exp'])
        # login
        if self.totp:
            twofactor_code = pyotp.TOTP(self.totp).now()
        data = {'password': passwd_hash,
                'username': username,
                # 'oauth_client_id': '',  # used in mobile app
                'twofactorcode': twofactor_code or '',
                'emailauth': email_code or '',
                'loginfriendlyname': auth_name or '',
                'captchagid': -1,
                'captcha_text': '',
                'emailsteamid': '',
                'rsatimestamp': rc['timestamp'],
                'remember_login': True,
                'donotcache': int(time.time() * 1000)}
        rc = self.r.post('https://steamcommunity.com/login/dologin/', data=data)
        open('log.log', 'w').write(rc.text)  # DEBUG
        rc = rc.json()

        if rc['success'] is False:
            if rc.get('emailauth_needed'):
                email_code = input('email auth code: ')
                self.login(username, passwd, email_code=email_code, auth_name=auth_name)
            elif rc.get('requires_twofactor'):
                twofactor_code = input('two factor code: ')
                self.login(username, passwd, twofactor_code=twofactor_code)
            elif rc.get('message') == 'Incorrect login.':
                print('Incorrect login.')
                raise BaseException
            else:
                # raise GsteamError(rc)
                print('unknown error')
                raise BaseException
        self.saveSession()
        return True

    def inventory(self, app_id=753, marketable_only=True):
        params = {'l': 'english',
                  'count': 2000}
        if marketable_only:
            params['market'] = 1
        url = 'https://steamcommunity.com/inventory/76561198011812285/%s/%s' % (app_id, self.currency)
        rc = self.r.get(url, params=params).json()
        open('smapi.log', 'w').write(json.dumps(rc))

        descs = {i['classid']: i for i in rc['descriptions']}
        # items = [descs[i['classid']] for i in rc['assets'] if descs[i['classid']].get('market_hash_name')]
        items = {}
        for i in rc['assets']:
            if not descs[i['classid']].get('market_hash_name'):  # not marketable?
                continue
            elif i['classid'] in items.keys():  # duplicate
                items[i['classid']]['amount'] += 1
                items[i['classid']]['asset_ids'].append(i['assetid'])
            else:
                items[i['classid']] = (descs[i['classid']])
                items[i['classid']]['contextid'] = i['contextid']
                items[i['classid']]['amount'] = 1
                items[i['classid']]['asset_ids'] = [i['assetid']]

        # names = [i['market_hash_name'] for i in items if i.get('market_hash_name')]

        return items

    def unpack(self, app_id, item_id):  # unpack booster
        data = {'appid': app_id,
                'communityitemid': item_id,
                'sessionid': self.session_id}
        self.r.headers['X-Requested-With'] = 'XMLHttpRequest'
        rc = self.r.post('https://steamcommunity.com/id/oczun/ajaxunpackbooster/', data=data).json()
        del self.r.headers['X-Requested-With']
        open('smapi.log', 'w').write(json.dumps(rc))
        return rc['success'] == 1

    def price(self, id, name):
        # time.sleep(random.randint(15, 25))
        time.sleep(random.randint(17, 25))
        # get item_nameid (this can be skipped when item_nameid is in database)
        # encode name?
        if name == 'MajorMinor':  # fix database
            name = 'Major-Minor'
        name = urllib.parse.quote(name)
        url = 'https://steamcommunity.com/market/listings/%s/%s' % (id, name)
        print(url)
        rc = self.r.get(url).text  # 753 = steam items?
        open('log.log', 'w').write(rc)
        if "You've made too many requests recently. Please wait and try your request again later." in rc:
            print("You've made too many requests recently. Please wait and try your request again later.")
            asd

        # # history parse (only volume for now)
        if 'var line1' in rc:
            history = {}
            history_raw = json.loads(re.search('var line1\=(\[.+\])', rc).group(1))
            for i in history_raw:
                i_date = parser.parse(i[0][:-4]).date()
                if i[0][-6:-4] != '01' and i_date in history.keys():
                    history[i_date] += int(i[2])
                else:
                    history[i_date] = int(i[2])

            # average volume
            days = 90
            days = min(datetime.date.today() - next(iter(history)), datetime.timedelta(days=days))  # days cannot be bigger than time since first transaction
            vol = sum([history[i] for i in history if i > datetime.date.today() - days]) / days.days  # average daily volume in last x days
        else:
            vol = 0

        item_nameid = re.search('Market_LoadOrderSpread\( ([0-9]+) \);', rc).group(1)

        # get price
        params = {'country': 'PL',
                  'language': 'english',
                  'currency': self.currency,
                  'item_nameid': item_nameid,
                  'two_factor': 0}
        rc = self.r.get('https://steamcommunity.com/market/itemordershistogram', params=params).json()
        open('smapi.log', 'w').write(json.dumps(rc))
        sell_min = int(rc['lowest_sell_order'] or 0) / 100
        buy_min = int(rc['highest_buy_order'] or 0) / 100
        sell = [(i[0], i[1]) for i in rc['sell_order_graph']]
        buy = [(i[0], i[1]) for i in rc['buy_order_graph']]
        return {'sell_min': sell_min,
                'sell': sell,
                'buy_min': buy_min,
                'buy': buy,
                'vol': vol}

    def orders(self):  # TODO: login required to work of course
        orders = {'buy': [],
                  'sell': []}
        # sell orders
        start = 0
        count = 100
        while True:
            params = {'query': '',
                      'start': start,
                      'count': count}
            rc = self.r.get('https://steamcommunity.com/market/mylistings/render/', params=params).json()
            for game_id in rc['assets']:
                for context_id in rc['assets'][game_id]:
                    for order_id in rc['assets'][game_id][context_id]:
                        order = rc['assets'][game_id][context_id][order_id]
                        orders['sell'].append({'game_id': order['appid'],
                                               'order_id': order['id'],
                                               'amount': order['amount'],
                                               'original_amount': order['original_amount'],
                                               'status': order['status'],  # 2 active listing
                                               'item_name': order['name'],  # market_name  market_hash_name
                                               'commodity': order['commodity'], })
                        # TODO: price in order['hovers']
            if count >= rc['total_count']:  # use num_active_listings instead?
                break
            start += count

        # buy orders
        rc = self.r.get('https://steamcommunity.com/market/').text
        bs = BeautifulSoup(rc, 'lxml')
        divs = bs.findAll('div', {'class': 'market_listing_row market_recent_listing_row'})
        for div in divs:
            order_id = int(div.attrs['id'].replace('mybuyorder_', ''))
            game_name = div.find('span', {'class': 'market_listing_game_name'}).text
            # item_name = div.find('span', {'class': 'market_listing_item_name'}).a.text
            game_id, market_hash_name = div.find('span', {'class': 'market_listing_item_name'}).a.attrs['href'].split('/')[-2:]
            market_hash_name = unquote(market_hash_name)
            item_id, item_name = re.search('([0-9]+?)\-(.+)', market_hash_name).groups()
            # item_name = unquote(item_name)  # unquote by bs?
            # amount = div.span()[0].span.text.replace(' @', '')
            # amount = div.find('span', {'class': 'market_listing_inline_buyorder_qty'}).text.replace(' @', '')
            amount, price = list(div.find('span', {'class': 'market_listing_price'}).strings)[1:]
            amount = amount.replace(' @', '')
            # price = price.strip()  # remove currency code
            price = re.match('([0-9\,]+).+', price.strip()).group(1)
            price = float(price.replace(',', '.'))
            orders['buy'].append({'order_id': order_id,
                                  'game_id': game_id,
                                  'game_name': game_name,
                                  'item_id': item_id,
                                  'item_name': item_name,
                                  'amount': amount,
                                  'price': price,
                                  'market_hash_name': market_hash_name})
        return orders

    def sell(self, appid, assetid, contextid, price):
        if price < 1:  # 0.15 -> 15
            price = int(price * 100)
        # fees
        if price < 20:
            price -= 2
        elif price < 30:
            price -= 3
        elif price < 40:
            price -= 4
        elif price < 50:
            price -= 6
        else:
            SmapiError('more fees reduction needs to be implemented')  # TODO
        data = {'amount': 1,
                'appid': appid,
                'assetid': assetid,
                'contextid': contextid,
                'price': price,
                'sessionid': self.session_id}
        print(data)
        self.r.headers['Referer'] = 'https://steamcommunity.com/id/oczun/inventory/'
        rc = self.r.post('https://steamcommunity.com/market/sellitem/', data=data).json()
        del self.r.headers['Referer']
        open('smapi.log', 'w').write(json.dumps(rc))
        if not rc:
            SmapiError('invalid response')
        elif not rc['success']:
            if rc['message'] == 'You already have a listing for this item pending confirmation. Please confirm or cancel the existing listing.':
                pass
            elif rc['message'] == 'You have too many listings pending confirmation. Please confirm or cancel some before attempting to list more.':
                raise SmapiError('You have too many listings pending confirmation. Please confirm or cancel some before attempting to list more.')
            else:
                print(rc)
            return False
        return True

    def buy(self, appid, market_hash_name, quantity, price, currency=6):
        quantity = int(quantity)
        if price < 0.03:  # minimum value
            price = 0.03
        price_total = int(price * 100 * int(quantity))
        data = {'appid': appid,
                'currency': currency,
                'market_hash_name': market_hash_name,
                'price_total': price_total,
                'quantity': quantity,
                'sessionid': self.session_id}
        print(data)
        self.r.headers['Referer'] = 'https://steamcommunity.com/market/listings/%s/%s' % (appid, market_hash_name)
        rc = self.r.post('https://steamcommunity.com/market/createbuyorder/', data=data).json()
        del self.r.headers['Referer']
        print(rc)
        if rc['success'] == 1:
            return rc['buy_orderid']
        if rc['success'] == 25:
            raise SmapiError('You need more wallet balance to make this order.')
        else:
            raise SmapiError('unknown status')

    def cancelBuy(self, order_id):
        data = {'buy_orderid': order_id,
                'sessionid': self.session_id}
        self.r.headers['Referer'] = 'https://steamcommunity.com/market/'
        self.r.headers['X-Requested-With'] = 'XMLHttpRequest'
        self.r.headers['X-Prototype-Version'] = '1.7'
        rc = self.r.post('https://steamcommunity.com/market/cancelbuyorder/', data=data).json()
        del self.r.headers['Referer']
        del self.r.headers['X-Requested-With']
        del self.r.headers['X-Prototype-Version']
        # print(rc)
        return rc['success'] == 1
