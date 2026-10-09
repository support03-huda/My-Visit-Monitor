# Copyright (c) 2026, huda and contributors
# For license information, please see license.txt
# File: mvm_visit_entry.py
# Purpose: Visit entry: check-in, check-out, the comparison with the customer location, and the manager
#          action that makes a check-in position the customer location.
# Created: 2026-10-05
# Last updated: 2026-10-09

# Frappe framework.
import frappe
# Translation function for messages shown to the user.
from frappe import _
# Base class of every DocType controller.
from frappe.model.document import Document
# Running numbers.
from frappe.model.naming import getseries
# Date, time and conversion helpers.
from frappe.utils import add_days, cint, cstr, flt, nowtime, today

# Who the logged-in employee is and which zones they cover.
from my_visit_monitor.permission import get_current_employee, get_employee_zones, is_manager
# Settings, distance and address lookup.
from my_visit_monitor.utils import (
	distance_in_metres,
	geocode_address,
	geofence_radius,
	get_settings,
	has_coordinates,
	location_required,
)


# Controller of MVM Visit Entry.
class MVMVisitEntry(Document):
	# Visit number.
	def autoname(self):
		# YY + company + running number, e.g. 2601000042
		company_id = cstr(get_settings().company_id or "01").strip().zfill(2)
		# Two-digit year + company id + 6-digit running number.
		self.name = f"{today()[2:4]}{company_id}{getseries('MVM-VISIT', 6)}"

	# Check in: runs once, when the visit is first saved.
	def before_insert(self):
		# Whose visit this is.
		self.set_employee()
		# The customer must be in the employee's zones.
		self.validate_customer_zone()

		# A new visit starts checked in.
		self.status = "Checked In"
		# Check-in date is today.
		self.checkin_date = today()
		# Check-in time is now.
		self.checkin_time = nowtime()
		# Not checked out yet.
		self.checkout_date = self.checkout_time = None
		# No check-out position yet.
		self.checkout_latitude = self.checkout_longitude = 0
		# So no accuracy of it either.
		self.checkout_accuracy = 0
		# Without a check-in position there is no accuracy to keep.
		if not has_coordinates(self.checkin_latitude, self.checkin_longitude):
			# Drop whatever was sent.
			self.checkin_accuracy = 0
		# The check-in position must be there when it is required.
		self.validate_location(self.checkin_latitude, self.checkin_longitude)

		# Position of the customer.
		self.set_customer_location()
		# Was the check-in at the customer?
		self.compare_with_customer_location("checkin", self.checkin_latitude, self.checkin_longitude)
		# Date of the next visit.
		self.set_next_visit_date()

	# The visit belongs to the employee of the logged-in user.
	def set_employee(self):
		# managers may log a visit on behalf of an employee through the API or an import
		if self.employee and is_manager():
			# Keep the employee the manager entered.
			return
		# Employee of the logged-in user.
		self.employee = get_current_employee()
		# The user has no employee record.
		if not self.employee:
			# Stop with a message.
			frappe.throw(
				_("No active MVM Employee is linked to the user {0}. Ask a manager to set the User on your employee record.").format(
					frappe.session.user
				)
			)

	# Field staff can only visit customers in their own zones.
	def validate_customer_zone(self):
		# Managers may log a visit for any customer.
		if is_manager():
			# Nothing to check.
			return
		# Zone of the customer.
		zone = frappe.db.get_value("MVM Customer", self.customer, "zone")
		# The employee does not cover that zone.
		if zone not in get_employee_zones(self.employee):
			# Stop with a message.
			frappe.throw(_("Customer {0} is not in one of your zones.").format(self.customer))

	# Stop when a position is required (MVM Settings) but was not captured.
	def validate_location(self, latitude, longitude):
		# A position is required and none was captured.
		if location_required() and not has_coordinates(latitude, longitude):
			# Stop with a message.
			frappe.throw(
				_("Your location could not be captured. Allow location access in the browser and try again.")
			)

	# Position of the customer: the one set on the customer, else its address looked up.
	def set_customer_location(self):
		# Name and address of the customer, for the address lookup.
		customer = frappe.db.get_value(
			"MVM Customer",
			self.customer,
			["customer_name", "company_name", "address_line_1", "address_line_2", "address_line_3", "city", "pincode", "state", "country"],
		)
		# Position set on the customer.
		latitude, longitude = frappe.db.get_value("MVM Customer", self.customer, ["latitude", "longitude"])
		# The customer has a position.
		if has_coordinates(latitude, longitude):
			# Use it.
			location = (latitude, longitude)
		# The customer has no position.
		else:
			# Look up the address; None when that fails.
			location = geocode_address(", ".join(cstr(part) for part in customer if part))
		# A position was found.
		if location:
			# Store it on the visit.
			self.customer_latitude, self.customer_longitude = location

	# Compare a position of the employee with the customer position.
	# `event` is "checkin" or "checkout"; the result is written to the fields of that event.
	def compare_with_customer_location(self, event, latitude, longitude):
		"""Record whether the employee was at the customer. A visit away from it is saved with a warning."""
		# True for the check-in, False for the check-out.
		checkin = event == "checkin"
		# Field with the sentence shown on the form.
		remark_field = "location_remark" if checkin else "checkout_location_remark"
		# Field with the distance in metres.
		distance_field = f"{event}_distance"
		# Field with Inside / Outside; the form colours the sentence green or red with it.
		status_field = f"{event}_location_status"

		# Allowed distance in metres (MVM Settings).
		radius = geofence_radius()
		# No sentence yet.
		self.set(remark_field, None)
		# No distance yet.
		self.set(distance_field, 0)
		# No status yet.
		self.set(status_field, None)
		# Radius 0 switches the comparison off.
		if not radius:
			# Nothing to compare.
			return
		# The position of the customer is unknown.
		if not has_coordinates(self.customer_latitude, self.customer_longitude):
			# Say so in the sentence.
			self.set(remark_field, _("Customer location is not known"))
			# Nothing to compare.
			return
		# The position of the employee is unknown.
		if not has_coordinates(latitude, longitude):
			# Say so in the sentence.
			self.set(
				remark_field,
				_("Check-in location was not captured") if checkin else _("Check-out location was not captured"),
			)
			# Nothing to compare.
			return

		# Distance between employee and customer, in metres.
		distance = distance_in_metres(latitude, longitude, self.customer_latitude, self.customer_longitude)
		# Keep the distance on the visit.
		self.set(distance_field, distance)
		# The employee is at the customer.
		if distance <= radius:
			# Sentence for a position inside the radius.
			self.set(remark_field, _("Within {0} m of the customer location").format(radius))
			# Shown in green.
			self.set(status_field, "Inside")
			# Done; no warning.
			return

		# Sentence for a position outside the radius, with the distance.
		self.set(
			remark_field,
			_("Not within {0} m of the customer location (about {1} m away)").format(radius, round(distance)),
		)
		# Shown in red.
		self.set(status_field, "Outside")
		# Warn the user; the visit is saved anyway.
		frappe.msgprint(
			_("The visit is saved, but you are not within {0} m of the customer location. You are about {1} m away.").format(
				radius, round(distance)
			),
			title=_("Outside Customer Location"),
			indicator="orange",
		)

	# Next visit = check-in date + the customer's follow-up days, unless a date was entered.
	def set_next_visit_date(self):
		# Follow-up interval of the customer, in days.
		days = cint(frappe.db.get_value("MVM Customer", self.customer, "next_followup_days"))
		# An interval is set and no date was entered.
		if days and not self.next_visit_date:
			# Check-in date plus that many days.
			self.next_visit_date = add_days(self.checkin_date, days)

	# Check out: called from the Check Out button with the position of the browser.
	@frappe.whitelist()
	def check_out(self, latitude=None, longitude=None, accuracy=None):
		# The user must be allowed to change this visit.
		self.check_permission("write")
		# A visit can only be checked out once.
		if self.checkout_date:
			# Stop with a message.
			frappe.throw(_("Visit {0} is already checked out.").format(self.name))
		# The check-out position must be there when it is required.
		self.validate_location(latitude, longitude)

		# Check-out date is today.
		self.checkout_date = today()
		# Check-out time is now.
		self.checkout_time = nowtime()
		# Check-out latitude.
		self.checkout_latitude = latitude
		# Check-out longitude.
		self.checkout_longitude = longitude
		# How exact the check-out position is, in metres; 0 when there is no position.
		self.checkout_accuracy = flt(accuracy) if has_coordinates(latitude, longitude) else 0
		# Was the check-out at the customer?
		self.compare_with_customer_location("checkout", latitude, longitude)
		# The visit is finished.
		self.status = "Checked Out"
		# Save the visit.
		self.save()

	# Manager action: the check-in position of this visit becomes the location of its customer.
	# Later visits to the customer are compared with this exact point instead of the looked-up address.
	@frappe.whitelist()
	def use_checkin_as_customer_location(self):
		# Field staff cannot change the location of a customer.
		if not is_manager():
			# Stop with a message.
			frappe.throw(_("Only a manager can set the customer location."), frappe.PermissionError)
		# A visit without a check-in position has nothing to copy.
		if not has_coordinates(self.checkin_latitude, self.checkin_longitude):
			# Stop with a message.
			frappe.throw(_("This visit has no check-in location."))

		# The customer of this visit.
		customer = frappe.get_doc("MVM Customer", self.customer)
		# Latitude of the check-in.
		customer.latitude = self.checkin_latitude
		# Longitude of the check-in.
		customer.longitude = self.checkin_longitude
		# Customers of the old database miss fields that are mandatory today; that must not block this.
		customer.flags.ignore_mandatory = True
		# Save the customer; the change shows in its history.
		customer.save()
