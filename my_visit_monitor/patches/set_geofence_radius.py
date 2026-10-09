# File: set_geofence_radius.py
# Purpose: One-time patch: stores the default geofence radius on sites that have none.
# Created: 2026-10-07
# Last updated: 2026-10-09

# Frappe framework.
import frappe

# The default radius (200 m).
from my_visit_monitor.utils import DEFAULT_GEOFENCE_RADIUS


# Frappe runs this once per site, during migrate.
def execute():
	# A single keeps no value for a field added after it was saved, and saving the settings form
	# would then store 0, which switches the location check off.
	# Plain SQL: tabSingles has no creation column, which frappe.db.get_value sorts on.
	saved = frappe.db.sql(
		"select `value` from `tabSingles` where `doctype` = %s and `field` = %s",
		("MVM Settings", "geofence_radius"),
	)
	# No radius was ever stored.
	if not saved or saved[0][0] is None:
		# Store the default.
		frappe.db.set_single_value("MVM Settings", "geofence_radius", DEFAULT_GEOFENCE_RADIUS)
