import httpx
import re
import urllib.parse
import json
import time
import base64
import datetime
from html import unescape
from dateutil import parser
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from steam import guard  # https://github.com/ValvePython/steam used for mobile confirmations, this should implemented without external library

from .exceptions import SmapiError

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


def hashPasswd(passwd: str,
               mod: str,
               exp: str) -> bytes:
    '''RSA encode password.'''
    mod = int(str(mod), 16)
    exp = int(str(exp), 16)
    rsa = RSA.construct((mod, exp))
    cipher = PKCS1_v1_5.new(rsa)
    return base64.b64encode(cipher.encrypt(passwd.encode()))


# def priceCutFee(price):  # almost good
#     price = price * 100
#     c_price = floor(price / 1.15)

#     if c_price + 2 >= price:  # lowest prices under minimum fees
#         return price - 2

#     steam_fee = floor(c_price * 0.05)
#     dev_fee = floor(c_price * 0.1)

#     while c_price + steam_fee + dev_fee < price:
#         c_price += 1
#         steam_fee = floor(c_price * 0.05)
#         dev_fee = floor(c_price * 0.1)

#     return c_price

def priceCutFee(_price: int) -> int:
    p = _price
    fee = 2  # <22
    p -= 21
    while True:  # TODO: refactorization
        if p > 0:
            p -= 11
            fee += 1
            if p > 11:
                p -= 1
                fee += 1
            if p > 0:
                p -= 11
                fee += 1
            else:
                break
        else:
            break
    return _price - fee


class Core:
    def __init__(self,
                 username: str,
                 passwd: str,
                 secrets: dict,
                 currency: int,  # default to USD?
                 country: str,  # default to Germany?
                 android_id: str) -> None:
        self.username = username
        self.passwd = passwd
        self.secrets = secrets
        # self.r.headers.encoding = 'utf8'  # temporary
        self.r = httpx.Client(timeout=300, headers=headers)
        self.currency = currency  # 6 PLN, 3 EUR, 18 UAH
        self.country = country  # PL, ?, UA
        self.android_id = android_id
        self.sa = guard.SteamAuthenticator(secrets=self.secrets)
        # load saved cookies/session
        try:
            with open('cookies.json', 'r') as f:
                self.r.cookies.update(json.load(f))
        except json.JSONDecodeError:  # file corupted or empty
            pass
        except FileNotFoundError:
            pass
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
        self.steam_id = re.search('g_steamID = "([0-9]+?)";', rc).group(1)
        self.saveSession()

    def saveSession(self) -> None:
        '''Saves cookies/session.'''
        # print([i for i in self.r.cookies.jar])
        with open('cookies.json', 'w') as f:
            json.dump(self.r.cookies.jar.__dict__, f)

    def login(self,
              username: str,
              passwd: str,
              email_code: str = None,
              auth_name: str = None,
              twofactor_code: str = None) -> bool:
        self.r.headers['X-Requested-With'] = 'XMLHttpRequest'
        data = {'username': username, 'donotcache': int(time.time() * 1000)}
        rc = self.r.post('https://steamcommunity.com/login/getrsakey/', data=data).json()
        if not rc['success']:
            return False
        passwd_hash = hashPasswd(passwd, rc['publickey_mod'], rc['publickey_exp'])
        # login
        # if self.totp:  # TODO: test it
        #     # twofactor_code = pyotp.TOTP(self.totp).now()
        #     twofactor_code = guard.generate_twofactor_code(self.totp)
        data = {'password': passwd_hash,
                'username': username,
                # 'oauth_client_id': '',  # used in mobile app
                'twofactorcode': twofactor_code or '',  # is it even working here?
                'emailauth': email_code or '',
                'loginfriendlyname': auth_name or '',
                'captchagid': -1,
                'captcha_text': '',
                'emailsteamid': '',
                'rsatimestamp': rc['timestamp'],
                'remember_login': True,
                'donotcache': int(time.time() * 1000)}
        rc = self.r.post('https://steamcommunity.com/login/dologin/', data=data)
        open('smapi.log', 'w').write(rc.text)  # DEBUG
        rc = rc.json()
        print(rc)

        if rc['success'] is False:
            if rc.get('emailauth_needed'):
                email_code = input('email auth code: ')
                self.login(username, passwd, email_code=email_code, auth_name=auth_name)
            elif rc.get('requires_twofactor'):
                print('two factor')
                if self.secrets:
                    # self.sa = guard.SteamAuthenticator(secrets=self.secrets)  # initted in __init__
                    twofactor_code = self.sa.get_code()
                else:
                    twofactor_code = input('two factor code: ')
                print(twofactor_code)
                return self.login(username, passwd, twofactor_code=twofactor_code)
            elif rc.get('message') == 'Incorrect login.':
                print('Incorrect login.')
                raise BaseException
            elif rc.get('message') == 'There have been too many login failures from your network in a short time period.  Please wait and try again later.':
                raise BaseException('ip blocked')
            else:
                # raise GsteamError(rc)
                print('unknown error')
                raise BaseException

        # self.steam_id = rc['transfer_parameters']['steamid']
        # data = {'steamid': self.steam_id,
        #         'token_secure': token,
        #         'auth': auth,
        #         'remember_login': False,  # ca it be True?
        #         'webcookie': webcookie}
        data = rc['transfer_parameters']
        del self.r.headers['X-Requested-With']
        # self.r.headers['Referer'] = 'https://steamcommunity.com/login/home/?goto='
        for url in rc['transfer_urls']:
            rc = self.r.post(url, data=data).text
            open('smapi.log', 'w').write(rc)
        # print({cookie.name: cookie.value for cookie in self.r.cookies.jar})
        rc = self.r.get('https://steamcommunity.com/my/goto').text  # canceles cookies - request is wrong here because there are two different session_ids for domains?
        open('smapi.log', 'w').write(rc)
        if 'javascript:Logout();' not in rc:
            raise SmapiError('unknown error during login')
        return True

    def inventory(self, app_id: int = 753, marketable_only: bool = True) -> dict:
        params = {'l': 'english',
                  'count': 2000}
        if marketable_only:
            params['market'] = 1
        url = 'https://steamcommunity.com/inventory/%s/%s/6' % (self.steam_id, app_id)  # 6 = contextid
        rc = self.r.get(url, params=params).json()
        # open('inventory.txt', 'w').write(json.dumps(rc))  # DEBUG
        assets = rc['assets']
        descriptions = rc['descriptions']
        while rc.get('more_items') == 1:
            params['start_assetid'] = rc['last_assetid']
            rc = self.r.get(url, params=params).json()
            # open('inventory.txt', 'w').write(json.dumps(rc))  # DEBUG
            assets.extend(rc['assets'])
            descriptions.extend(rc['descriptions'])  # TODO: it's ugly
        # print('Marketable ttems in inventory: %s' % len(assets))
        # if rc.get('error') and 'The request is a duplicate and the action has already occurred in the past, ignored this time' in rc.get('error'):
        #     time.sleep(30)
        #     rc = self.r.get(url, params=params).json()
        # open('smapi.log', 'w').write(json.dumps(rc))

        descs = {i['classid']: i for i in descriptions}
        # items = [descs[i['classid']] for i in rc['assets'] if descs[i['classid']].get('market_hash_name')]
        items = {}
        for i in assets:
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

    def unpack(self, app_id, item_id) -> bool:  # unpack booster
        data = {'appid': app_id,
                'communityitemid': item_id,
                'sessionid': self.session_id}
        self.r.headers['X-Requested-With'] = 'XMLHttpRequest'
        rc = self.r.post('https://steamcommunity.com/id/%s/ajaxunpackbooster/' % self.username, data=data).json()
        del self.r.headers['X-Requested-With']
        open('smapi.log', 'w').write(json.dumps(rc))
        return rc['success'] == 1

    def price(self, id, name):
        # time.sleep(random.randint(15, 25))
        # time.sleep(random.randint(17, 25))
        # get item_nameid (this can be skipped when item_nameid is in database)
        # encode name?
        print(name)
        name = urllib.parse.quote(name)
        url = 'https://steamcommunity.com/market/listings/%s/%s' % (id, name)
        print(url)
        # try:
        #     rc = self.r.get(url)
        #     open('smapi.log', 'wb').write(rc.content)
        #     rc = rc.text  # 753 = steam items?
        # except httpx.exceptions.NetworkError:
        #     print('>>> network error')
        #     time.sleep(10)
        #     rc = self.r.get(url).text  # 753 = steam items?
        rc = self.r.get(url).text
        open('smapi.log', 'w').write(rc)
        if 'There was an error communicating with the network. Please try again later.' in rc or 'There was an error getting listings for this item. Please try again later.' in rc or '502 Bad Gateway' in rc or 'An error occurred while processing your request.' in rc or '504 Gateway Time-out' in rc or 'The site is currently unavailable.  Please try again later.' in rc:
            print('temporary error, waiting 10 seconds and retrying')
            time.sleep(10)
            rc = self.r.get(url).text  # 753 = steam items?
            open('smapi.log', 'w').write(rc)
        if "You've made too many requests recently. Please wait and try your request again later." in rc:
            print("You've made too many requests recently. Please wait and try your request again later.")
            raise BaseException("You've made too many requests recently. Please wait and try your request again later.")
        if 'This item can no longer be bought or sold on the Community Market.' in rc:
            print('>>>> REMOVED')
            return None
        elif 'There are no listings for this item.' in rc:
            print('>>>>>>>  00000')
            return None
        # elif 'There is no price history available for this item yet.' in rc:
        #     print('new item, no history yet?')
        #     return None

        # # history parse (only volume for now)
        if 'var line1' in rc:
            history = {}
            history_raw = json.loads(re.search(r'var line1\=(\[.+\])', rc).group(1))
            for i in history_raw:
                i_date = parser.parse(i[0][:-4]).date()
                if i[0][-6:-4] != '01' and i_date in history.keys():
                    history[i_date] += int(i[2])
                else:
                    history[i_date] = int(i[2])

            # average volume
            days = 90
            days = min(datetime.date.today() - next(iter(history)), datetime.timedelta(days=days))  # days cannot be bigger than time since first transaction
            try:
                vol = sum([history[i] for i in history if i > datetime.date.today() - days]) / days.days  # average daily volume in last x days
            except ZeroDivisionError:  # no history, this item appeared today
                vol = 0
        else:
            vol = 0

        item_nameid = re.search(r'Market_LoadOrderSpread\( ([0-9]+) \);', rc).group(1)

        # get price
        params = {'country': self.country,
                  'language': 'english',
                  'currency': self.currency,
                  'item_nameid': item_nameid,
                  'two_factor': 0}
        rc = self.r.get('https://steamcommunity.com/market/itemordershistogram', params=params)
        # if 'The server is temporarily unable to service your request.  Please try again' in rc.text or 'The site is currently unavailable.  Please try again later.' in rc.text or 'An error occurred while processing your request.' in rc.text or '502 Bad Gateway' in rc.text or '500 Internal Server Error' in rc.text:
        if rc.is_error:
            print(rc.status_code)
            print('temporary error, retrying after 15 seconds')
            time.sleep(15)
            rc = self.r.get('https://steamcommunity.com/market/itemordershistogram', params=params)
        open('smapi.log', 'w').write(rc.text)
        rc = rc.json()
        if rc['success'] == 16:  # DEBUG?
            print('to many requests? waiting 15 seconds and retrying')
            time.sleep(15)
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

    def orders(self) -> dict:  # TODO: login required to work of course
        orders = {'buy': [],
                  'sell': []}
        # sell orders
        start = 0
        count = 100
        # TODO: sell from listings instead of assets - parse more info
        while True:
            params = {'query': '',
                      'start': start,
                      'count': count,
                      'norender': 1}
            rc = self.r.get('https://steamcommunity.com/market/mylistings/render/', params=params)
            # if '502 Bad Gateway' in rc.text or 'The site is currently unavailable.  Please try again later.' in rc.text:
            if rc.is_error:
                print('502 Bad Gateway / site temporary unavailable')
                time.sleep(5)
                rc = self.r.get('https://steamcommunity.com/market/mylistings/render/', params=params)
            open('smapi.log', 'w').write(rc.text)
            rc = rc.json()
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
        for i in rc['buy_orders']:
            print(i)
            if 'description' not in i:  # TODO: parse data instead
                continue
            orders['buy'].append({'order_id': i['buy_orderid'],
                                  'game_id': i['appid'],
                                  'game_name': i['description']['type'],
                                  'item_id': i['description']['market_fee_app'],
                                  'item_name': i['description']['name'],
                                  'amount': i['quantity_remaining'],
                                  'price': float(i['price']) / 100,
                                  'market_hash_name': i['hash_name']})
        return orders

    def sell(self, appid, assetid, contextid, price) -> bool:
        # if price >= 4.01:  # TODO: remove it/configure it
        #     # raise SmapiError('expensive item')  # TODO
        #     print('expensive item')
        #     return False
        _price = int(round(price * 100, 0))
        _price = priceCutFee(_price)
        data = {'amount': 1,
                'appid': appid,
                'assetid': assetid,
                'contextid': contextid,
                'price': _price,
                'sessionid': self.session_id}
        print(data)
        self.r.headers['Referer'] = 'https://steamcommunity.com/id/%s/inventory?modal=1&market=1' % self.username
        rc = self.r.post('https://steamcommunity.com/market/sellitem/', data=data)
        if '502 Bad Gateway' in rc.text or rc.status_code == 503:
            print('502/503, retrying in 5 seconds')
            time.sleep(5)
            rc = self.r.post('https://steamcommunity.com/market/sellitem/', data=data)
        open('smapi.log', 'w').write(rc.text)
        rc = rc.json()
        del self.r.headers['Referer']
        if not rc:
            raise SmapiError('invalid response')
        elif not rc['success']:
            if rc['message'] == 'You already have a listing for this item pending confirmation. Please confirm or cancel the existing listing.':
                pass
            elif rc['message'] == 'You have too many listings pending confirmation. Please confirm or cancel some before attempting to list more.':
                # raise SmapiError('You have too many listings pending confirmation. Please confirm or cancel some before attempting to list more.')
                self.confirmTrades()
                self.sell(appid=appid, assetid=assetid, contextid=contextid, price=price)
            elif rc['message'] == 'You cannot sell any items until your previous action completes.':
                print('You cannot sell any items until your previous action completes.')
                time.sleep(60 * 5)
                return self.sell(appid=appid, assetid=assetid, contextid=contextid, price=price)
            elif rc['message'] == 'There was a problem listing your item. Refresh the page and try again.':
                print('There was a problem listing your item. Refresh the page and try again.')
                time.sleep(60 * 5)
                # time.sleep(random.randint(5, 20))
                return self.sell(appid=appid, assetid=assetid, contextid=contextid, price=price)
            else:
                print(rc)
            return False
        return True

    def buy(self, appid, market_hash_name, quantity, price):
        quantity = int(quantity)
        print(price)
        if price < 0.03:  # minimum value
            price = 0.03
        price_total = int(round(price * 100, 0) * int(quantity))
        data = {'appid': appid,
                'currency': self.currency,
                'market_hash_name': market_hash_name,
                'price_total': price_total,
                'quantity': quantity,
                'sessionid': self.session_id}
        print(data)
        self.r.headers['Referer'] = f'https://steamcommunity.com/market/listings/{appid}/{market_hash_name}'
        rc = self.r.post('https://steamcommunity.com/market/createbuyorder/', data=data).json()
        del self.r.headers['Referer']
        print(rc)
        if rc['success'] == 1:
            return rc['buy_orderid']
        elif rc['success'] == 29 and rc['message'] == 'You already have an active buy order for this item. You will need to either cancel that order, or wait for it to be fulfilled before you can place a new order.':
            return True
        elif rc['success'] in (8, 16, 20, 42):  # 'Sorry! We had trouble hearing back from the Steam servers about your order. Double check whether or not your order has actually been created or filled. If not, then please try again later.'
            raise BaseException('Sorry! We had trouble hearing back from the Steam servers about your order. Double check whether or not your order has actually been created or filled. If not, then please try again later.')
            print('Sorry! We had trouble hearing back from the Steam servers about your order. Double check whether or not your order has actually been created or filled. If not, then please try again later.')
            time.sleep(60)
            return self.buy(appid=appid, market_hash_name=market_hash_name, quantity=quantity, price=price)
        elif rc['success'] == 25:
            raise SmapiError('You need more wallet balance to make this order.')
        else:
            raise SmapiError('unknown status')

    def cancelBuy(self, order_id) -> bool:
        data = {'buy_orderid': order_id,
                'sessionid': self.session_id}
        self.r.headers['Referer'] = 'https://steamcommunity.com/market/'
        self.r.headers['X-Requested-With'] = 'XMLHttpRequest'
        self.r.headers['X-Prototype-Version'] = '1.7'
        rc = self.r.post('https://steamcommunity.com/market/cancelbuyorder/', data=data)
        if '502 Bad Gateway' in rc.text:
            print('502 Bad Gateway')
            rc = self.r.post('https://steamcommunity.com/market/cancelbuyorder/', data=data)
        open('smapi.log', 'w').write(rc.text)
        rc = rc.json()
        del self.r.headers['Referer']
        del self.r.headers['X-Requested-With']
        del self.r.headers['X-Prototype-Version']
        # print(rc)
        return rc['success'] == 1

    def cleanNotifications(self) -> None:
        self.r.get('https://steamcommunity.com/id/%s/inventory/' % self.username)

    def confirmTrades(self) -> bool:
        params = {'l': 'english',
                  'p': self.android_id,
                  'a': self.steam_id,
                  'k': base64.b64encode(self.sa.get_confirmation_key('conf')).decode('utf8'),
                  't': self.sa.get_time(),
                  'm': 'android',
                  'tag': 'conf'}
        rc = self.r.get('https://steamcommunity.com/mobileconf/conf', params=params).text
        open('smapi.log', 'w').write(rc)
        if "You don't have anything to confirm right now." in rc:
            return True
        else:
            items = re.findall(r'id="multiconf_[0-9]+" data-confid="([0-9]+)" data-key="([0-9]+)"', rc)
            cids = [i[0] for i in items]
            cks = [i[1] for i in items]
            if len(cids) > 0:
                data = {'op': 'allow',
                        'p': self.android_id,
                        'a': self.steam_id,
                        'k': base64.b64encode(self.sa.get_confirmation_key('conf')).decode('utf8'),
                        't': self.sa.get_time(),
                        'm': 'android',
                        'tag': 'conf',
                        'cid[]': cids,
                        'ck[]': cks}
                print(data)
                rc = self.r.post('https://steamcommunity.com/mobileconf/multiajaxop', data=data).json()
                # open('smapi.log', 'w').write(json.dumps(rc))
                if rc['success'] is not True:
                    print(rc)
                    raise SmapiError('unknown error during sell confirmation')
            return True

    def gems(self):
        rc = self.r.get('https://steamcommunity.com/tradingcards/boostercreator/').text
        open('smapi.log', 'w').write(rc)
        boosters = json.loads(re.search(r'(\[{"appid".+}\])', rc).group(1))
        for i, d in enumerate(boosters):
            market_hash_name = '%s-%s Booster Pack' % (d['appid'], unescape(d['name']).replace('/', '-'))
            p = self.price(753, market_hash_name)
            if not p:  # there is booster pack?
                continue
            boosters[i].update(p)
            boosters[i]['price'] = int(boosters[i]['price'])
            yield boosters[i]
        # return boosters
