import requests
import re
import urllib.parse
import time
import random
import pyotp
import base64
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from bs4 import BeautifulSoup
from urllib.parse import unquote
try:
    from cookielib import LWPCookieJar
except ImportError:
    from http.cookiejar import LWPCookieJar
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

    def price(self, id, name):
        # time.sleep(random.randint(15, 25))
        time.sleep(random.randint(17, 25))
        # get item_nameid (this can be skipped when item_nameid is in database)
        # encode name?
        if name == 'MajorMinor':  # fix database
            name = 'Major-Minor'
        name = urllib.parse.quote('%s Booster Pack' % name)
        url = 'https://steamcommunity.com/market/listings/753/%s-%s' % (id, name)
        print(url)
        rc = self.r.get(url).text  # 753 = (normal?) booster pack
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
        rc = self.r.get('https://steamcommunity.com/market/itemordershistogram', params=params).json()
        # if rc['lowest_sell_order'] is None:
        #     return None
        if rc['highest_buy_order'] is None:
            return 0
        # return int(rc['lowest_sell_order'])
        return int(rc['highest_buy_order'])

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
            game_id, item_name = div.find('span', {'class': 'market_listing_item_name'}).a.attrs['href'].split('/')[-2:]
            item_id, item_name = re.search('([0-9]+\-)?(.+)', item_name).groups()
            item_name = unquote(item_name)  # unquote by bs?
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
