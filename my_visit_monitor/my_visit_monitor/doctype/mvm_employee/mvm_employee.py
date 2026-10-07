# Copyright (c) 2026, huda and contributors
# For license information, please see license.txt
# File: mvm_employee.py
# Purpose: Employee master, with the zones the employee covers.
# Created: 2026-10-05
# Last updated: 2026-10-07

# Frappe framework.
import frappe
# Translation function for messages shown to the user.
from frappe import _
# Base class of every DocType controller.
from frappe.model.document import Document

# Helpers that build and protect the A00001 style code.
from my_visit_monitor.utils import next_letter_code, validate_code_letter


# Controller of MVM Employee.
class MVMEmployee(Document):
	# Code like A00001, from the first letter of the employee name.
	def autoname(self):
		# Set the employee code.
		self.name = next_letter_code(self.doctype, self.employee_name)

	# Keep the code letter, link the login and reject repeated zones.
	def validate(self):
		# Check the first letter of the employee name.
		validate_code_letter(self, "employee_name")

		# the employee is recognised at login through the user with the same email
		if not self.user and self.email and frappe.db.exists("User", self.email):
			# Link that user to the employee.
			self.user = self.email

		# Zones listed on the employee.
		zones = [row.zone for row in self.zones]
		# A zone appears twice.
		if len(zones) != len(set(zones)):
			# Stop with a message.
			frappe.throw(_("The same zone is listed more than once."))
