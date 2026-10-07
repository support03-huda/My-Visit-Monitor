# File: set_geofence_radius.py
# Purpose: One-time patch: stores the default geofence radius on sites that have none.
# Created: 2026-10-07
# Last updated: 2026-10-07

# Frappe framework.
import frappe

# The default radius (50 m).
from my_visit_monitor.utils import DEFAULT_GEOFENCE_RADIUS


# Frappe runs this once per site, during migrate.
def execute():
	# A single keeps no value for a field added after it was saved, and saving the settings form
	# would then store 0, which switches the location check off.
	saved = frappe.db.get_value("Singles", {"doctype": "MVM Settings", "field": "geofence_radius"}, "value")
	# No radius was ever stored.
	if saved is None:
		# Store the default.
		frappe.db.set_single_value("MVM Settings", "geofence_radius", DEFAULT_GEOFENCE_RADIUS)
