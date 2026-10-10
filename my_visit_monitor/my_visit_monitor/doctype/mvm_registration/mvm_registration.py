# Copyright (c) 2026, huda and contributors
# For license information, please see license.txt
# File: mvm_registration.py
# Purpose: Registration of a self-registered login, approved or rejected once by an admin or a team manager.
#          Approval sets the employee, its zones and manager; the person then gets the email to set their password.
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

# The approver's own employee, and whether they are an admin.
from my_visit_monitor.permission import get_current_employee, is_manager
# Who may approve.
from my_visit_monitor.registration import is_approver

# Role every approved login gets: field staff ("user").
APPROVED_ROLE = "MVM User"


# Controller of MVM Registration.
class MVMRegistration(Document):
	# Values the form needs: may this user decide, and who is their own employee (the default manager).
	def onload(self):
		# Approve and Reject are shown only to approvers.
		self.set_onload("can_decide", is_approver())
		# A team manager approves people into their own team; an admin chooses.
		self.set_onload("default_manager", None if is_manager() else get_current_employee())

	# Only an admin or a team manager may decide, and only once.
	def check_can_decide(self):
		# Field staff and visitors cannot approve.
		if not is_approver():
			# Stop with a message.
			frappe.throw(_("Only an administrator or a manager can approve or reject a registration."), frappe.PermissionError)
		# Already approved or rejected.
		if self.status != "Pending":
			# Stop with a message.
			frappe.throw(_("This registration is already {0}.").format(_(self.status).lower()))

	# Approve: the login becomes a normal user and gets an employee record.
	# `employee` links an existing employee; without it a new employee is created.
	# `zones` (list of zone names) and `reporting_to` (the manager) are set on the employee when given.
	@frappe.whitelist()
	def approve(self, employee=None, zones=None, reporting_to=None):
		# Only an approver, and only while pending.
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
		# The login is linked to an employee already.
		elif linked:
			# Keep that one.
			employee = linked
		# No employee yet: create one.
		else:
			# A team manager who gives no manager puts the new person in their own team.
			if not reporting_to and not is_manager():
				# The approver's own employee becomes the manager.
				reporting_to = get_current_employee()
			# New employee for this login.
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

		# Zones and manager given in the approval dialog.
		self.set_employee_details(employee, zones, reporting_to)

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

		# Without an outgoing email account Frappe only shows a notice and sends nothing,
		# so the approver has to set the password by hand.
		if not has_outgoing_email():
			# The employee, so the form can open it to add zones, and that no email went out.
			return {"employee": employee, "mail_sent": False}
		# Email with the link to set the password; the person can log in after that.
		try:
			# Frappe's welcome email (subject "Welcome to ...", link to set the password).
			user.send_welcome_mail_to_user()
			# It went into the email queue.
			mail_sent = True
		# The email could not be prepared.
		except Exception:
			# Keep a record in the Error Log.
			frappe.log_error(title="MVM registration welcome email failed")
			# The approver is told to set the password by hand.
			mail_sent = False
		# The employee, so the form can open it to add zones, and whether the email went out.
		return {"employee": employee, "mail_sent": mail_sent}

	# Add the zones and set the manager of the employee, when given.
	def set_employee_details(self, employee, zones, reporting_to):
		# The dialog sends the zones as JSON text.
		zones = frappe.parse_json(zones) if isinstance(zones, str) else (zones or [])
		# Nothing to change.
		if not zones and not reporting_to:
			# Done.
			return
		# The employee record.
		record = frappe.get_doc("MVM Employee", employee)
		# Zones the employee has already.
		current = {row.zone for row in record.zones}
		# Every zone chosen in the dialog.
		for zone in zones:
			# Only zones that are not on the employee yet.
			if zone and zone not in current:
				# Add it.
				record.append("zones", {"zone": zone})
				# Remember it, so it is not added twice.
				current.add(zone)
		# A manager was given.
		if reporting_to:
			# Set it.
			record.reporting_to = reporting_to
		# Employees from the old database miss fields that are mandatory today.
		record.flags.ignore_mandatory = True
		# Save the employee.
		record.save(ignore_permissions=True)

	# Reject: the login stays unusable.
	@frappe.whitelist()
	def reject(self, remarks=None):
		# Only an approver, and only while pending.
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


# True when the site can send email: an enabled default outgoing Email Account, or a mail server in the site config.
def has_outgoing_email():
	# Email account set up under Tools > Email Account.
	if frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1}):
		# Email can be sent.
		return True
	# Mail server written in the site configuration instead.
	return bool(frappe.conf.get("mail_server"))
