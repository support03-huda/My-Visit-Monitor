import math
import re

import frappe
from frappe import _
from frappe.utils import cint, flt

CODE_DIGITS = 5
DEFAULT_GEOFENCE_RADIUS = 50


def get_settings():
	return frappe.get_cached_doc("MVM Settings")


# A setting added after the settings were last saved reads as None, not as its default.
def location_required():
	value = get_settings().require_location
	return True if value is None else bool(cint(value))


def geofence_radius():
	"""Metres from the customer's location within which a check-in counts as at the customer; 0 is off."""
	value = get_settings().geofence_radius
	return DEFAULT_GEOFENCE_RADIUS if value is None else cint(value)


def code_letter(text):
	"""First letter or digit of `text`, upper-cased. Master codes start with it."""
	match = re.search(r"[A-Za-z0-9]", text or "")
	return match.group(0).upper() if match else "X"


def next_letter_code(doctype, text):
	"""Next code like A00001: the first letter of `text` plus a running number per letter."""
	letter = code_letter(text)
	last = frappe.db.sql(
		f"select name from `tab{doctype}` where name regexp %s order by name desc limit 1 for update",
		(f"^{letter}[0-9]{{{CODE_DIGITS}}}$",),
	)
	number = cint(last[0][0][1:]) + 1 if last else 1
	if number >= 10**CODE_DIGITS:
		frappe.throw(_("No more codes are available for the letter {0}").format(letter))
	return f"{letter}{number:0{CODE_DIGITS}d}"


def validate_code_letter(doc, fieldname):
	"""The code is derived from the first letter of `fieldname`, so that letter cannot change later."""
	if doc.is_new() or not doc.has_value_changed(fieldname):
		return
	if code_letter(doc.get(fieldname)) != doc.name[:1].upper():
		frappe.throw(
			_("{0} must keep starting with '{1}' to match the code {2}").format(
				_(doc.meta.get_label(fieldname)), doc.name[:1].upper(), doc.name
			)
		)


def has_coordinates(latitude, longitude):
	return bool(flt(latitude) or flt(longitude))


def distance_in_metres(lat1, lon1, lat2, lon2):
	"""Great-circle distance between two points."""
	lat1, lon1, lat2, lon2 = (math.radians(flt(v)) for v in (lat1, lon1, lat2, lon2))
	a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
	return 6371000 * 2 * math.asin(math.sqrt(a))


def geocode_address(address):
	"""Return (latitude, longitude) of `address` from Google Geocoding, or None.

	Never raises: a failed lookup must not block a check-in.
	"""
	api_key = get_settings().get_password("google_maps_api_key", raise_exception=False)
	if not api_key or not address:
		return None

	import requests

	try:
		response = requests.get(
			"https://maps.googleapis.com/maps/api/geocode/json",
			params={"address": address, "key": api_key},
			timeout=10,
		)
		response.raise_for_status()
		data = response.json()
		if data.get("status") != "OK":
			if data.get("status") != "ZERO_RESULTS":
				frappe.log_error(title="MVM geocoding failed", message=frappe.as_json(data))
			return None
		location = data["results"][0]["geometry"]["location"]
		return flt(location["lat"]), flt(location["lng"])
	except Exception:
		frappe.log_error(title="MVM geocoding failed")
		return None
