#!/usr/bin/env python

import boto3
import functools
import json
import os
import psycopg2
import requests

from collections.abc import Callable
from psycopg2.extras import RealDictCursor
from rich import print
from tenacity import retry, wait_exponential, stop_after_attempt
from typing import Any, Concatenate, Dict, Iterable, ParamSpec, Self, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


class RDS:
	_connection: psycopg2.extensions.connection | None

	def __init__(
		self: Self,
		rds_instance_name: str = 'coll',
		rds_db_name: str = 'postgres',
		region_name: str = 'us-east-2',
	) -> None:
		self.client = boto3.client('rds', region_name=region_name) # type: ignore
		self._rds_info = self.client.describe_db_instances(
			DBInstanceIdentifier=rds_instance_name,
		)['DBInstances'][0]

		self._rds_host = self._rds_info['Endpoint']['Address']
		self._rds_port = self._rds_info['Endpoint']['Port']
		self._rds_db_name = rds_db_name

		sm = boto3.client(
			service_name='secretsmanager',
			region_name=region_name,
		)
		self._rds_username, self._rds_password = json.loads(
			sm.get_secret_value(
				SecretId=self._rds_info['MasterUserSecret']['SecretArn'],
			)['SecretString'],
		).values()

		self._connection = None
		self._connect()


	@property
	def aws_global_bundle_path(self: Self) -> str:
		certs_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'certs')
		bundle_path = os.path.join(certs_path, 'global-bundle.pem')

		os.makedirs(certs_path, exist_ok=True)
		if not os.path.exists(bundle_path):
			resp = requests.get('https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem')
			resp.raise_for_status()
			with open(bundle_path, 'wb+') as f:
				f.write(resp.content)

		return bundle_path


	@property
	def connected(self: Self) -> bool:
		return bool(self._connection and not self._connection.closed)


	def close(self: Self) -> None:
		if self.connected:
			pass


	def _connect(self: Self) -> None:
		self.close()
		self._connection = psycopg2.connect(
			host=self._rds_host,
			port=self._rds_port,
			database=self._rds_db_name,
			user=self._rds_username,
			password=self._rds_password,
			sslmode='verify-full',
			sslrootcert=self.aws_global_bundle_path,
		)


	@staticmethod
	def _reconnect(
		f: Callable[Concatenate[RDS, P], R]
	) -> Callable[Concatenate[RDS, P], R]:
		@functools.wraps(f)
		def wrapper(db: RDS, *args: P.args, **kwargs: P.kwargs) -> R:
			if not db.connected:
				db._connect()
			try:
				return f(db, *args, **kwargs)
			except psycopg2.Error:
				db.close()
				raise

		return wrapper


	@retry(stop=stop_after_attempt(3), wait=wait_exponential())
	@_reconnect
	def query(self: Self, q: str) -> Iterable[Dict[str, Any]]:
		assert(self._connection is not None)
		with self._connection:
			with self._connection.cursor(
				cursor_factory=RealDictCursor,
			) as cur:
				cur.execute(q)
				while (row:=cur.fetchone()):
					yield {k: v for k, v in row.items()}


def main():
	db = RDS()
	for row in db.query(f"select version();"):
		print(row)


if __name__ == '__main__':
	main()
