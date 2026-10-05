# Copyright (c) 2026, huda and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from my_visit_monitor.utils import next_letter_code, validate_code_letter


class MVMCustomer(Document):
	def autoname(self):
		self.name = next_letter_code(self.doctype, self.company_name)

	def validate(self):
		validate_code_letter(self, "company_name")
