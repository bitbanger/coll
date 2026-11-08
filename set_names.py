#!/usr/bin/env python

from collections.abc import Callable
import json as _json
import re
import time
from typing import Any, Dict, Iterable, List, TypeAlias, TypeVar, cast

from curl_cffi import requests

from rich import print
from rich.progress import track
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from cw import cw
from db import RDS


JSON: TypeAlias = None | int | bool | float | str | List["JSON"] | Dict[str, "JSON"]


F = TypeVar("F", bound=Callable[..., Any])
def typed_retry(f: F) -> F:
	return cast(F, retry(
		stop=stop_after_attempt(3),
		wait=wait_exponential(),
		retry=retry_if_exception(lambda e: '404' not in str(e)),
	)(f))


@typed_retry
def curl(
	curl_fn: str,
	json: bool = True,
) -> str | JSON:
	curl_lines = []
	if len(curl_fn.split('\n')) > 1:
		curl_lines = curl_fn.split('\n')
	else:
		with open(curl_fn, 'r') as f:
			curl_lines = list(f.readlines())

	assert(len(curl_lines) > 1)

	url = None
	headers = {}
	for line in curl_lines:
		line = line.strip()
		match (opt:=line.split()[0]):
			case 'curl':
				url = line.split("'")[1]
			case '-H':
				k = line.split("'")[1].split(':')[0]
				v = line.split("'")[1].split(':')[1].strip()
				headers[k] = v
			case _:
				print(f"Unknown curl option -{opt}")

	assert(not not url)
	assert(not not headers)

	resp = requests.get(
		url,
		headers=headers,
		impersonate="chrome",
	)
	resp.raise_for_status()

	return resp.text if not json else _json.loads(resp.text)


def sports() -> List[str]:
	return sorted(set(re.findall(
		r'/([a-z]*)-cards"',
		str(curl('curls/scp_main.sh', json=False)),
	)))


def sets(sport: str) -> JSON:
	with open('curls/set_names.sh', 'r') as f:
		return curl(f.read().format(sport=sport))


def populate_db_sport_sets(sport: str) -> None:
	db = RDS()
	sp_sets: List[Dict[str, str]] = sets(sport) # type: ignore
	db.insert(
		'scp.sets',
		({
			'pid': row['value'],
			'sport': sport,
			'name': row['label'],
		} for row in sp_sets if row.get('value')),
	)


def populate_db_sets() -> None:
	for sport in track(sports(), description='Downloading: '):
		try:
			populate_db_sport_sets(sport)
		except Exception as e:
			if '404' in str(e):
				print(f"{sport} 404")
				continue
			else:
				raise e
		print(f"{sport} done")
		time.sleep(2)
	pass


def populate_db_cards(gid: str) -> Iterable[Dict[str, Any]]:
	db = RDS()
	rec = list(db.query(f"select sport, name from scp.sets where gid='{gid}'"))[0]

	url_name = rec['sport'] + '-cards-' + rec['name'].replace(' ', '-')

	with open('curls/fetch.sh', 'r') as f:
		curl_txt = f.read()
	cursor = 0
	while True:
		try:
			resp: Dict[str, Any] | None = curl(
				curl_txt.format(name=url_name, cursor=cursor),
				json=True,
			) # type: ignore
		except Exception as e:
			if '404' in str(e):
				if '-cards-' in url_name:
					url_name = url_name.split('-cards-')[-1]
					continue
				else:
					raise e
			else:
				raise e

		if resp is None:
			break

		now = int(time.time())
		for p in resp['products']:
			yield {
				'gid': gid,
				'console_uri': p['consoleUri'],
				'has_product': p['hasProduct'],
				'pid': p['id'],
				'image_uri': p['imageUri'],
				'is_card': p['isCard'],
				'is_proof_coin': p['isProofCoin'],
				'price1': p['price1'],
				'price2': p['price2'],
				'price3': p['price3'],
				'price_change': p['priceChange'],
				'price_change_percentage': p['priceChangePercentage'],
				'price_change_sign': p['priceChangeSign'],
				'print_run': p['printRun'],
				'product_name': p['productName'],
				'product_uri': p['productUri'],
				'show_cover_art': p['showCoverArt'],
				'wishlist_has_product': p['wishlistHasProduct'],
				'scraped_at': now,
			}

		if 'cursor' not in resp:
			break

		cursor = int(resp['cursor'])


def main():
	RDS().insert(
		'scp.cards',
		populate_db_cards('G100007'),
	)


if __name__ == '__main__':
	main()
