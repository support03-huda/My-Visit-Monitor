# Copyright (c) 2026, huda and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from my_visit_monitor.utils import next_letter_code, validate_code_letter


class MVMEmployee(Document):
	def autoname(self):
		self.name = next_letter_code(self.doctype, self.employee_name)

	def validate(self):
		validate_code_letter(self, "employee_name")

		# the employee is recognised at login through the user with the same email
		if not self.user and self.email and frappe.db.exists("User", self.email):
			self.user = self.email

		if self.reporting_to and self.reporting_to == self.name:
			frappe.throw(_("An employee cannot report to themselves."))

		zones = [row.zone for row in self.zones]
		if len(zones) != len(set(zones)):
			frappe.throw(_("The same zone is listed more than once."))
