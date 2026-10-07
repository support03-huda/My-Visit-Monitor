# File: utils.py
# Purpose: Shared helpers: settings, master codes (A00001), distance and address lookup.
# Created: 2026-10-05
# Last updated: 2026-10-07

# Trigonometry for the distance.
import math
# Regular expressions.
import re

# Frappe framework.
import frappe
# Translation function for messages shown to the user.
from frappe import _
# cint: to whole number, flt: to decimal number.
from frappe.utils import cint, flt

# Digits after the letter of a master code.
CODE_DIGITS = 5
# Radius in metres used when none is stored in MVM Settings.
DEFAULT_GEOFENCE_RADIUS = 50


# The MVM Settings record (cached).
def get_settings():
	# Read it from the cache.
	return frappe.get_cached_doc("MVM Settings")


# A setting added after the settings were last saved reads as None, not as its default.
def location_required():
	# Stored value of the Require Location checkbox.
	value = get_settings().require_location
	# Never saved means required.
	return True if value is None else bool(cint(value))


# Allowed distance between check-in and customer.
def geofence_radius():
	"""Metres from the customer's location within which a check-in counts as at the customer; 0 is off."""
	# Stored value of the Geofence Radius.
	value = get_settings().geofence_radius
	# Never saved means the default.
	return DEFAULT_GEOFENCE_RADIUS if value is None else cint(value)


# Letter a master code starts with.
def code_letter(text):
	"""First letter or digit of `text`, upper-cased. Master codes start with it."""
	# First letter or digit in the text.
	match = re.search(r"[A-Za-z0-9]", text or "")
	# Upper-cased; X when the text has none.
	return match.group(0).upper() if match else "X"


# Next free code for a master record.
def next_letter_code(doctype, text):
	"""Next code like A00001: the first letter of `text` plus a running number per letter."""
	# Letter of the code.
	letter = code_letter(text)
	# Highest existing code with that letter; the row is locked until the save is done.
	last = frappe.db.sql(
		f"select name from `tab{doctype}` where name regexp %s order by name desc limit 1 for update",
		(f"^{letter}[0-9]{{{CODE_DIGITS}}}$",),
	)
	# Next number; 1 for the first record.
	number = cint(last[0][0][1:]) + 1 if last else 1
	# All 99999 numbers of this letter are used.
	if number >= 10**CODE_DIGITS:
		# Stop with a message.
		frappe.throw(_("No more codes are available for the letter {0}").format(letter))
	# Letter + number padded with zeros.
	return f"{letter}{number:0{CODE_DIGITS}d}"


# Keep the name and the code in step.
def validate_code_letter(doc, fieldname):
	"""The code is derived from the first letter of `fieldname`, so that letter cannot change later."""
	# A new record, or a name that did not change.
	if doc.is_new() or not doc.has_value_changed(fieldname):
		# Nothing to check.
		return
	# The name now starts with another letter than the code.
	if code_letter(doc.get(fieldname)) != doc.name[:1].upper():
		# Stop with a message.
		frappe.throw(
			_("{0} must keep starting with '{1}' to match the code {2}").format(
				_(doc.meta.get_label(fieldname)), doc.name[:1].upper(), doc.name
			)
		)


# True when a position was captured; 0, 0 means no position.
def has_coordinates(latitude, longitude):
	# At least one of the two is not zero.
	return bool(flt(latitude) or flt(longitude))


# Distance between two positions (haversine formula).
def distance_in_metres(lat1, lon1, lat2, lon2):
	"""Great-circle distance between two points."""
	# Degrees to radians.
	lat1, lon1, lat2, lon2 = (math.radians(flt(v)) for v in (lat1, lon1, lat2, lon2))
	# Haversine of the angle between the two points.
	a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
	# Angle times the radius of the earth (6371 km), in metres.
	return 6371000 * 2 * math.asin(math.sqrt(a))


# Position of an address, from Google.
def geocode_address(address):
	"""Return (latitude, longitude) of `address` from Google Geocoding, or None.

	Never raises: a failed lookup must not block a check-in.
	"""
	# Google Maps API key from MVM Settings.
	api_key = get_settings().get_password("google_maps_api_key", raise_exception=False)
	# No key or no address.
	if not api_key or not address:
		# No lookup.
		return None

	# HTTP client; loaded only when a lookup is made.
	import requests

	# The lookup may fail in many ways.
	try:
		# Ask Google for the position of the address.
		response = requests.get(
			"https://maps.googleapis.com/maps/api/geocode/json",
			params={"address": address, "key": api_key},
			timeout=10,
		)
		# Treat an HTTP error as a failure.
		response.raise_for_status()
		# Answer of Google.
		data = response.json()
		# Google found no position.
		if data.get("status") != "OK":
			# `ZERO_RESULTS` just means an unknown address; anything else is a real error.
			if data.get("status") != "ZERO_RESULTS":
				# Record the error in the Error Log.
				frappe.log_error(title="MVM geocoding failed", message=frappe.as_json(data))
			# No position.
			return None
		# Position of the first result.
		location = data["results"][0]["geometry"]["location"]
		# Latitude and longitude as numbers.
		return flt(location["lat"]), flt(location["lng"])
	# Network error, timeout or unexpected answer.
	except Exception:
		# Record the error in the Error Log.
		frappe.log_error(title="MVM geocoding failed")
		# No position.
		return None
