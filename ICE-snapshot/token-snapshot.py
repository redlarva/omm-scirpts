import argparse
import concurrent.futures
import json
import os
import time

import csv

from iconsdk.builder.call_builder import CallBuilder
from iconsdk.icon_service import IconService
from iconsdk.providers.http_provider import HTTPProvider
from concurrent.futures import wait
from checkscore.repeater import retry

sICX_RATE = 1068878173082825969
EXA = 10 ** 18

NETWORK_ID = {
  "MAINNET": 1,
  "YEOUIDO": 3,
}

MAINNET_ADDRESS = {
  'LENDING_POOL': 'cxcb455f26a2c01c686fa7f30e1e3661642dd53c0d',
  'oICX': 'cx0fb973aaab3a26cc99022ba455e5bdfed1d6f0d9'
}
YEOUIDO_ADDRESS = {
  'LENDING_POOL': 'cx082dc739288fa8780998f8b1cfcd4c428c85c819',
  'oICX': 'cxc58f32a437c8e5a5fcb8129626662f2252ad2678'
}

addresses = {
  f'{NETWORK_ID["MAINNET"]}': MAINNET_ADDRESS,
  f'{NETWORK_ID["YEOUIDO"]}': YEOUIDO_ADDRESS,
}

connections = {
  f'{NETWORK_ID["MAINNET"]}': 'http://35.84.178.200',
  f'{NETWORK_ID["YEOUIDO"]}': 'https://bicon.net.solidwallet.io',
}


def argumentParser():
  parser = argparse.ArgumentParser()

  parser.add_argument("-tkn", "--token", help="Token", type=str, default="oICX")
  parser.add_argument("-nid", "--nid", help="NID", type=int, default="1")

  args = parser.parse_args()

  return args


class TokenSnapshot(object):
  def __init__(self, nid):
    super(TokenSnapshot, self).__init__()

    self.wallets = []
    self.data = []
    self.data_csv = []
    server_url = connections[f'{nid}']
    self.icon_service = IconService(HTTPProvider(server_url, 3))

    self.addresses = addresses[f'{nid}']
    self.total_ICX = 0
    self.total_sICX = 0
    self.principal_total_sICX = 0
    self.principal_total_ICX = 0

  def _get_icx_balance(self, wallet):
    return self.icon_service.get_balance(wallet)

  @retry(Exception, tries=10, delay=1, back_off=2)
  def _call_tx(self, contract, method, params):
    params = {} if params is None else params
    call = CallBuilder() \
      .from_('hx91bf040426f226b3bfcd2f0b5967bbb0320525ce') \
      .to(contract) \
      .method(method) \
      .params(params) \
      .build()
    response = self.icon_service.call(call)
    return response

  def load_wallets(self):
    with open('ICE-snapshot/oICX-holders.json', 'r') as f:
      deposit_wallets = json.load(f)
    self.wallets.extend(deposit_wallets)

  def snapshot(self, _token):
    self.token = _token
    # for wallet in self.wallets:
    #   self._get_balances(wallet)
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(32, os.cpu_count())) as executor:
      executor.map(self._get_balances, self.wallets)

    _data = self._get_data()
    _sum_ICX = 0
    _sum = 0
    for item in _data:
      _sum_ICX += item['balance_ICX']
      _sum += item['balance']

    print(f"The sum of {_token} balances is: {_sum} ({_sum_ICX})")

    with open(f'{int(time.time())}_{token}-holders.json', 'w') as outfile:
      json.dump(_data, outfile)

    header = ['wallet', 'principal_balance', 'principal_balance_ICX', 'balance',
              'balance_ICX']

    with open(f'{int(time.time())}_{token}-holders.csv', 'w', encoding='UTF8',
              newline='') as f:
      writer = csv.writer(f)
      writer.writerow(header)
      writer.writerows(self._get_csv_data())
      writer.writerow([])
      writer.writerow(
          ["TOTAL", self.principal_total_sICX, self.principal_total_ICX,
           self.total_sICX, self.total_ICX])

  def _get_balances(self, wallet):
    _token_address = self.addresses[self.token]
    _balance = self._call_tx(_token_address, 'balanceOf', {'_owner': wallet})
    _balance = int(_balance, 16)
    if _balance > 0:
      _principalBalances = self._call_tx(_token_address, 'principalBalanceOf',
                                         {'_user': wallet})
      _csv_row = [wallet, int(_principalBalances, 16),
                  int(_principalBalances, 16) * sICX_RATE // EXA, _balance,
                  _balance * sICX_RATE // EXA]
      _row = {
        "wallet": _csv_row[0],
        "principal_balance": _csv_row[1],
        "principal_balance_ICX": _csv_row[2],
        "balance": _csv_row[3],
        "balance_ICX": _csv_row[4],
      }
      self.total_ICX += _csv_row[4]
      self.total_sICX += _csv_row[3]
      self.principal_total_ICX += _csv_row[2]
      self.principal_total_sICX += _csv_row[1]
      self.data.append(_row)
      self.data_csv.append(_csv_row)

  def _get_csv_data(self):
    return sorted(self.data_csv, reverse=True, key=lambda _row: _row[4])

  def _get_data(self):
    return sorted(self.data, reverse=True, key=lambda _row: _row['balance'])


if __name__ == '__main__':
  args = argumentParser()
  nid = args.nid
  token = args.token
  print(nid, token)
  before = time.perf_counter()
  instance = TokenSnapshot(nid)

  instance.load_wallets()
  print(len(instance.wallets))

  after = time.perf_counter()
  print(f"The time taken to fetch wallets: {after - before} seconds")

  instance.snapshot(token)

  after = time.perf_counter()
  print(f"The time taken to calculate: {after - before} seconds")
