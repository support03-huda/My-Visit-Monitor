# Copyright (c) 2026, huda and contributors
# For license information, please see license.txt
# File: mvm_customer.py
# Purpose: Customer master.
# Created: 2026-10-05
# Last updated: 2026-10-07

# Base class of every DocType controller.
from frappe.model.document import Document

# Helpers that build and protect the A00001 style code.
from my_visit_monitor.utils import next_letter_code, validate_code_letter


# Controller of MVM Customer.
class MVMCustomer(Document):
	# Code like A00001, from the first letter of the company name.
	def autoname(self):
		# Set the customer code.
		self.name = next_letter_code(self.doctype, self.company_name)

	# The company name must keep the first letter the code was made from.
	def validate(self):
		# Check the first letter of the company name.
		validate_code_letter(self, "company_name")
