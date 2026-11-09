#!/usr/bin/env python

from collections.abc import Callable
import json as _json
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Self, TypeAlias, TypeVar, cast

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


class SCP:
	def __init__(self: Self, db: Optional[RDS] = None) -> None:
		self.db = db if db is not None else RDS()


	def fetch_categories(self: Self) -> List[str]:
		return sorted(set(re.findall(
			r'/([a-z]*)-cards"',
			str(curl('curls/scp_main.sh', json=False)),
		)))


	def fetch_set_list(self: Self, category: str) -> Iterable[Dict[str, Any]]:
		with open('curls/set_names.sh', 'r') as f:
			resp: List[Dict[str, str]] = curl(
				f.read().format(category=category),
				json=True,
			) # type: ignore
			now = int(time.time())
			for row in resp:
				yield {
					**row,
					'etl_category': category,
					'etl_time': now,
				}


	def fetch_cards(self: Self, set_id: str) -> Iterable[Dict[str, Any]]:
		rec = list(self.db.query(f"select etl_category, label from scp_raw.sets where value='{set_id}'"))[0]

		url_set_name = rec['etl_category'] + '-cards-' + rec['label'].replace(' ', '-')

		with open('curls/fetch.sh', 'r') as f:
			curl_txt = f.read()
		cursor = 0
		while True:
			try:
				resp: Dict[str, Any] | None = curl(
					curl_txt.format(name=url_set_name, cursor=cursor),
					json=True,
				) # type: ignore
			except Exception as e:
				if '404' in str(e) and '-cards-' in url_set_name:
					url_set_name = url_set_name.split('-cards-')[-1]
					continue
				raise e

			if resp is None:
				break

			now = int(time.time())
			for p in resp['products']:
				yield {
					**p,
					'etl_set_id': set_id,
					'etl_url_set_name': url_set_name,
					'etl_time': now,
				}

			if 'cursor' not in resp:
				break

			cursor = int(resp['cursor'])


	def db_populate_sets(self: Self) -> None:
		for category in track(self.fetch_categories(), description='Downloading: '):
			try:
				self.db.insert('scp_raw.sets', self.fetch_set_list(category), create_table=True)
			except Exception as e:
				if '404' in str(e):
					print(f"{category} 404")
					continue
				else:
					raise e
			print(f"{category} done")
			time.sleep(2)
		pass


	def db_populate_cards(self: Self, set_id: str) -> None:
		self.db.insert('scp_raw.cards', self.fetch_cards(set_id), create_table=True)


	def set_id(self: Self, category: str, name: str) -> str:
		return list(self.db.query(f"select value from scp_raw.sets where lower(etl_category)='{category.lower()}' and lower(label)='{name.lower()}'"))[0]['value']


def main():
	scp = SCP()
	scp.db_populate_cards(scp.set_id('magic', 'magic reality fracture'))
	quit()
	# scp.db_populate_sets()
	# scp.db_populate_cards('G59903') # FIN
	# scp.db_populate
	'''
	for row in scp.fetch_set_list('magic'):
		print(row)
	'''
	'''
	RDS().insert(
		'scp_raw.cards',
		populate_db_cards('G100007'),
	)
	'''


if __name__ == '__main__':
	main()
