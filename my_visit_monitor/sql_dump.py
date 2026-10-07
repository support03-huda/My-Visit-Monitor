"""Read the INSERT statements of a phpMyAdmin / mysqldump SQL file into rows."""

import re
from collections import defaultdict

INSERT = re.compile(r"INSERT INTO `(\w+)` \(([^)]*)\) VALUES\s*", re.S)
ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "Z": "\x1a"}


def parse_inserts(text):
	"""Return {table: [row, ...]} with every row as a {column: value} dict.

	Strings stay strings, bare numbers become int or float, NULL becomes None.
	Binary (0x...) values are dropped to None.
	"""
	tables = defaultdict(list)
	pos = 0
	while match := INSERT.search(text, pos):
		table = match.group(1)
		columns = [column.strip().strip("`") for column in match.group(2).split(",")]
		pos = match.end()
		while True:
			values, pos = _read_tuple(text, pos)
			tables[table].append(dict(zip(columns, values, strict=False)))
			pos = _skip_space(text, pos)
			if text[pos] != ",":
				break
			pos += 1
	return dict(tables)


def _skip_space(text, pos):
	while text[pos].isspace():
		pos += 1
	return pos


def _read_tuple(text, pos):
	pos = _skip_space(text, pos)
	if text[pos] != "(":
		raise ValueError(f"Expected a row at position {pos}")
	pos += 1
	values = []
	while True:
		pos = _skip_space(text, pos)
		if text[pos] == "'":
			value, pos = _read_string(text, pos + 1)
		else:
			end = pos
			while text[end] not in ",)":
				end += 1
			value, pos = _convert(text[pos:end].strip()), end
		values.append(value)
		pos = _skip_space(text, pos)
		if text[pos] == ")":
			return values, pos + 1
		pos += 1


def _read_string(text, pos):
	parts = []
	while True:
		char = text[pos]
		if char == "\\":
			parts.append(ESCAPES.get(text[pos + 1], text[pos + 1]))
			pos += 2
		elif char == "'":
			if text[pos + 1] != "'":
				return "".join(parts), pos + 1
			parts.append("'")
			pos += 2
		else:
			parts.append(char)
			pos += 1


def _convert(token):
	if token.upper() == "NULL" or token.lower().startswith("0x"):
		return None
	try:
		return int(token)
	except ValueError:
		pass
	try:
		return float(token)
	except ValueError:
		return token
