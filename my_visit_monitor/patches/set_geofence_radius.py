import frappe

from my_visit_monitor.utils import DEFAULT_GEOFENCE_RADIUS


def execute():
	# A single keeps no value for a field added after it was saved, and saving the settings form
	# would then store 0, which switches the location check off.
	saved = frappe.db.get_value("Singles", {"doctype": "MVM Settings", "field": "geofence_radius"}, "value")
	if saved is None:
		frappe.db.set_single_value("MVM Settings", "geofence_radius", DEFAULT_GEOFENCE_RADIUS)
