# Copyright (c) 2026, huda and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import getseries
from frappe.utils import add_days, cint, cstr, nowtime, today

from my_visit_monitor.permission import get_current_employee, get_employee_zones, is_manager
from my_visit_monitor.utils import (
	distance_in_metres,
	geocode_address,
	geofence_radius,
	get_settings,
	has_coordinates,
	location_required,
)


class MVMVisitEntry(Document):
	def autoname(self):
		# YY + company + running number, e.g. 2601000042
		company_id = cstr(get_settings().company_id or "01").strip().zfill(2)
		self.name = f"{today()[2:4]}{company_id}{getseries('MVM-VISIT', 6)}"

	def before_insert(self):
		self.set_employee()
		self.validate_customer_zone()

		self.status = "Checked In"
		self.checkin_date = today()
		self.checkin_time = nowtime()
		self.checkout_date = self.checkout_time = None
		self.checkout_latitude = self.checkout_longitude = 0
		self.validate_location(self.checkin_latitude, self.checkin_longitude)

		self.set_customer_location()
		self.compare_with_customer_location()
		self.set_next_visit_date()

	def set_employee(self):
		# managers may log a visit on behalf of an employee through the API or an import
		if self.employee and is_manager():
			return
		self.employee = get_current_employee()
		if not self.employee:
			frappe.throw(
				_("No active MVM Employee is linked to the user {0}. Ask a manager to set the User on your employee record.").format(
					frappe.session.user
				)
			)

	def validate_customer_zone(self):
		if is_manager():
			return
		zone = frappe.db.get_value("MVM Customer", self.customer, "zone")
		if zone not in get_employee_zones(self.employee):
			frappe.throw(_("Customer {0} is not in one of your zones.").format(self.customer))

	def validate_location(self, latitude, longitude):
		if location_required() and not has_coordinates(latitude, longitude):
			frappe.throw(
				_("Your location could not be captured. Allow location access in the browser and try again.")
			)

	def set_customer_location(self):
		customer = frappe.db.get_value(
			"MVM Customer",
			self.customer,
			["customer_name", "company_name", "address_line_1", "address_line_2", "address_line_3", "city", "pincode", "state", "country"],
		)
		latitude, longitude = frappe.db.get_value("MVM Customer", self.customer, ["latitude", "longitude"])
		if has_coordinates(latitude, longitude):
			location = (latitude, longitude)
		else:
			location = geocode_address(", ".join(cstr(part) for part in customer if part))
		if location:
			self.customer_latitude, self.customer_longitude = location

	def compare_with_customer_location(self):
		"""Record whether the check-in was at the customer. A visit away from it is saved with a warning."""
		radius = geofence_radius()
		self.checkin_distance = 0
		self.location_remark = None
		if not radius:
			return
		if not has_coordinates(self.customer_latitude, self.customer_longitude):
			self.location_remark = _("Customer location is not known")
			return
		if not has_coordinates(self.checkin_latitude, self.checkin_longitude):
			self.location_remark = _("Check-in location was not captured")
			return

		self.checkin_distance = distance_in_metres(
			self.checkin_latitude, self.checkin_longitude, self.customer_latitude, self.customer_longitude
		)
		if self.checkin_distance <= radius:
			self.location_remark = _("Within {0} m of the customer location").format(radius)
			return

		self.location_remark = _("Not within {0} m of the customer location (about {1} m away)").format(
			radius, round(self.checkin_distance)
		)
		frappe.msgprint(
			_("The visit is saved, but you are not within {0} m of the customer location. You are about {1} m away.").format(
				radius, round(self.checkin_distance)
			),
			title=_("Outside Customer Location"),
			indicator="orange",
		)

	def set_next_visit_date(self):
		days = cint(frappe.db.get_value("MVM Customer", self.customer, "next_followup_days"))
		if days and not self.next_visit_date:
			self.next_visit_date = add_days(self.checkin_date, days)

	@frappe.whitelist()
	def check_out(self, latitude=None, longitude=None):
		self.check_permission("write")
		if self.checkout_date:
			frappe.throw(_("Visit {0} is already checked out.").format(self.name))
		self.validate_location(latitude, longitude)

		self.checkout_date = today()
		self.checkout_time = nowtime()
		self.checkout_latitude = latitude
		self.checkout_longitude = longitude
		self.status = "Checked Out"
		self.save()
