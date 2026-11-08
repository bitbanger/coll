import csv as _csv
import os
from types import TracebackType
from typing import Any, Dict, Self


class cw:
	def __init__(self: Self, fn: str) -> None:
		self.fn = fn
		self.cw = None


	def __enter__(self: Self) -> Self:
		os.makedirs(os.path.dirname(os.path.abspath(self.fn)), exist_ok=True)
		self.f = open(self.fn, 'w+')
		return self


	def __exit__(
		self: Self,
		exc_type: type[BaseException] | None,
		exc_val: BaseException | None,
		exc_tb: TracebackType | None,
	) -> bool | None:
		if self.f is not None:
			self.f.close()
		self.f = None
		return None


	def writerow(self: Self, row: Dict[str, Any]) -> None:
		assert(self.f is not None)
		if self.cw is None:
			self.cw = _csv.DictWriter(self.f, fieldnames=row.keys())
			self.cw.writeheader()
		self.cw.writerow(row)


	def write(self: Self, row: Dict[str, Any]) -> None:
		return self.writerow(row)
