# Copyright (c) 2026, huda and contributors
# For license information, please see license.txt
# File: mvm_registration.py
# Purpose: Registration of a self-registered login, approved or rejected once by an administrator.
#          On approval the person gets the email to set their password.
# Created: 2026-10-10
# Last updated: 2026-10-10

# Frappe framework.
import frappe
# Translation function for messages shown to the user.
from frappe import _
# Base class of every DocType controller.
from frappe.model.document import Document
# The current date and time.
from frappe.utils import now_datetime

# Who may approve.
from my_visit_monitor.registration import is_approver

# Role every approved login gets: field staff ("user").
APPROVED_ROLE = "MVM User"


# Controller of MVM Registration.
class MVMRegistration(Document):
	# Only an administrator may decide, and only once.
	def check_can_decide(self):
		# Field staff and visitors cannot approve.
		if not is_approver():
			# Stop with a message.
			frappe.throw(_("Only an administrator can approve or reject a registration."), frappe.PermissionError)
		# Already approved or rejected.
		if self.status != "Pending":
			# Stop with a message.
			frappe.throw(_("This registration is already {0}.").format(_(self.status).lower()))

	# Approve: the login becomes a normal user and gets an employee record.
	# `employee` links an existing employee; without it a new employee is created.
	@frappe.whitelist()
	def approve(self, employee=None):
		# Only an administrator, and only while pending.
		self.check_can_decide()

		# The login of the registration.
		user = frappe.get_doc("User", self.user)
		# A desk user, not a website-only user.
		user.user_type = "System User"
		# Allowed to log in.
		user.enabled = 1
		# Roles the login has now.
		roles = [row.role for row in user.roles]
		# The field staff role is missing.
		if APPROVED_ROLE not in roles:
			# Add it.
			user.append("roles", {"role": APPROVED_ROLE})
		# Managers may not edit users themselves; this one change is checked above.
		user.save(ignore_permissions=True)

		# Employee already linked to this login, if any.
		linked = frappe.db.get_value("MVM Employee", {"user": self.user})
		# An existing employee was chosen.
		if employee:
			# The chosen employee belongs to another login.
			other = frappe.db.get_value("MVM Employee", employee, "user")
			# Refuse to move an employee from one login to another.
			if other and other != self.user:
				# Stop with a message.
				frappe.throw(_("Employee {0} already belongs to login {1}.").format(employee, other))
			# The chosen employee.
			record = frappe.get_doc("MVM Employee", employee)
			# Link it to this login.
			record.user = self.user
			# Employees from the old database miss fields that are mandatory today.
			record.flags.ignore_mandatory = True
			# Save the employee.
			record.save(ignore_permissions=True)
			# Remember which employee it is.
			employee = record.name
		# The login is linked to an employee already.
		elif linked:
			# Keep that one.
			employee = linked
		# No employee yet.
		else:
			# New employee for this login; zones are added by the administrator afterwards.
			record = frappe.get_doc(
				{
					"doctype": "MVM Employee",
					"employee_name": self.full_name or self.email,
					"email": self.email,
					"user": self.user,
				}
			)
			# Create it.
			record.insert(ignore_permissions=True)
			# Remember which employee it is.
			employee = record.name

		# Approved.
		self.status = "Approved"
		# Employee of this login.
		self.employee = employee
		# Who approved.
		self.decided_by = frappe.session.user
		# When.
		self.decided_on = now_datetime()
		# Save the registration.
		self.save(ignore_permissions=True)

		# Email with the link to set the password; the person can log in after that.
		try:
			# Frappe's welcome email (subject "Welcome to ...", link to set the password).
			user.send_welcome_mail_to_user()
			# It went into the email queue.
			mail_sent = True
		# The email could not be prepared (for example no outgoing email account).
		except Exception:
			# Keep a record in the Error Log.
			frappe.log_error(title="MVM registration welcome email failed")
			# The administrator is told to set the password by hand.
			mail_sent = False
		# The employee, so the form can open it to add zones, and whether the email went out.
		return {"employee": employee, "mail_sent": mail_sent}

	# Reject: the login stays unusable.
	@frappe.whitelist()
	def reject(self, remarks=None):
		# Only an administrator, and only while pending.
		self.check_can_decide()
		# Switch the login off.
		frappe.db.set_value("User", self.user, "enabled", 0)
		# Rejected.
		self.status = "Rejected"
		# Why, if given.
		self.remarks = remarks
		# Who rejected.
		self.decided_by = frappe.session.user
		# When.
		self.decided_on = now_datetime()
		# Save the registration.
		self.save(ignore_permissions=True)
