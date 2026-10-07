# File: sql_dump.py
# Purpose: Reads a MySQL dump (.sql) without a database. Used by legacy_import.py.
# Created: 2026-10-07
# Last updated: 2026-10-07

"""Read the INSERT statements of a phpMyAdmin / mysqldump SQL file into rows."""

# Regular expressions.
import re
# Dictionary that creates missing entries.
from collections import defaultdict

# Start of an INSERT statement: table name and column list.
INSERT = re.compile(r"INSERT INTO `(\w+)` \(([^)]*)\) VALUES\s*", re.S)
# Backslash escapes used inside MySQL strings.
ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "Z": "\x1a"}


# Read every INSERT statement of the file.
def parse_inserts(text):
	"""Return {table: [row, ...]} with every row as a {column: value} dict.

	Strings stay strings, bare numbers become int or float, NULL becomes None.
	Binary (0x...) values are dropped to None.
	"""
	# Table name -> rows.
	tables = defaultdict(list)
	# Current position in the text.
	pos = 0
	# Next INSERT statement.
	while match := INSERT.search(text, pos):
		# Table name.
		table = match.group(1)
		# Column names, without the back quotes.
		columns = [column.strip().strip("`") for column in match.group(2).split(",")]
		# Continue after `VALUES`.
		pos = match.end()
		# One INSERT holds many rows.
		while True:
			# Read one row.
			values, pos = _read_tuple(text, pos)
			# Store it as {column: value}.
			tables[table].append(dict(zip(columns, values, strict=False)))
			# Skip to what follows the row.
			pos = _skip_space(text, pos)
			# No comma: that was the last row.
			if text[pos] != ",":
				# Leave the row loop.
				break
			# Step over the comma.
			pos += 1
	# Plain dictionary for the caller.
	return dict(tables)


# Position of the next character that is not white space.
def _skip_space(text, pos):
	# While at a space, tab or line end.
	while text[pos].isspace():
		# Move on.
		pos += 1
	# Position of the next real character.
	return pos


# Read one row `(value, value, ...)`; returns its values and the position after it.
def _read_tuple(text, pos):
	# Skip white space before the row.
	pos = _skip_space(text, pos)
	# A row starts with `(`.
	if text[pos] != "(":
		# The file is not what we expect.
		raise ValueError(f"Expected a row at position {pos}")
	# Step over the `(`.
	pos += 1
	# Values of this row.
	values = []
	# One value per round.
	while True:
		# Skip white space before the value.
		pos = _skip_space(text, pos)
		# A quoted string.
		if text[pos] == "'":
			# Read up to the closing quote.
			value, pos = _read_string(text, pos + 1)
		# A number, NULL or binary value.
		else:
			# Find where the value ends.
			end = pos
			# Until the next comma or the end of the row.
			while text[end] not in ",)":
				# Move on.
				end += 1
			# Convert the value and continue after it.
			value, pos = _convert(text[pos:end].strip()), end
		# Add the value to the row.
		values.append(value)
		# Skip white space after the value.
		pos = _skip_space(text, pos)
		# End of the row.
		if text[pos] == ")":
			# Return the values and the position after the `)`.
			return values, pos + 1
		# Step over the comma.
		pos += 1


# Read a quoted string, resolving \\ escapes and doubled quotes.
def _read_string(text, pos):
	# Pieces of the string.
	parts = []
	# One character per round.
	while True:
		# Current character.
		char = text[pos]
		# A backslash escape.
		if char == "\\":
			# Add the character it stands for.
			parts.append(ESCAPES.get(text[pos + 1], text[pos + 1]))
			# Step over both characters.
			pos += 2
		# A quote.
		elif char == "'":
			# A single quote ends the string.
			if text[pos + 1] != "'":
				# Return the string and the position after the quote.
				return "".join(parts), pos + 1
			# Two quotes stand for one quote.
			parts.append("'")
			# Step over both quotes.
			pos += 2
		# Any other character.
		else:
			# Add it.
			parts.append(char)
			# Move on.
			pos += 1


# Turn an unquoted value into None, int, float or text.
def _convert(token):
	# NULL and binary data.
	if token.upper() == "NULL" or token.lower().startswith("0x"):
		# No value.
		return None
	# Whole number?
	try:
		# Yes.
		return int(token)
	# Not a whole number.
	except ValueError:
		# Try the next type.
		pass
	# Decimal number?
	try:
		# Yes.
		return float(token)
	# Not a number.
	except ValueError:
		# Keep it as text.
		return token
