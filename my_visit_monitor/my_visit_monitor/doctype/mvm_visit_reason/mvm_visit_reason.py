# Copyright (c) 2026, huda and contributors
# For license information, please see license.txt
# File: mvm_visit_reason.py
# Purpose: Visit reason master.
# Created: 2026-10-05
# Last updated: 2026-10-07

# Base class of every DocType controller.
from frappe.model.document import Document

# Helpers that build and protect the A00001 style code.
from my_visit_monitor.utils import next_letter_code, validate_code_letter


# Controller of MVM Visit Reason.
class MVMVisitReason(Document):
	# Code like A00001, from the first letter of the description.
	def autoname(self):
		# Set the reason code.
		self.name = next_letter_code(self.doctype, self.description)

	# The description must keep the first letter the code was made from.
	def validate(self):
		# Check the first letter of the description.
		validate_code_letter(self, "description")
