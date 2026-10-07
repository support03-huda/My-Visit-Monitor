# File: permission.py
# Purpose: Who may see which customers and visits. Registered in hooks.py.
# Created: 2026-10-05
# Last updated: 2026-10-07

# Frappe framework.
import frappe

# Users with one of these roles see everything.
MANAGER_ROLES = {"MVM Manager", "System Manager"}


# True for Administrator and for users with a manager role.
def is_manager(user=None):
	# Default to the logged-in user.
	user = user or frappe.session.user
	# Administrator, or a user holding a manager role.
	return user == "Administrator" or bool(MANAGER_ROLES.intersection(frappe.get_roles(user)))


# Employee of a user.
def get_current_employee(user=None):
	"""Code of the active MVM Employee linked to the user, if any."""
	# Default to the logged-in user.
	user = user or frappe.session.user
	# Active employee whose User field is this user.
	employee = frappe.db.get_value("MVM Employee", {"user": user, "inactive": 0})
	# No employee is linked to the user.
	if not employee:
		# the employee may have been created before the user existed, so User was never filled
		email = frappe.db.get_value("User", user, "email")
		# Active employee with the same email address.
		employee = email and frappe.db.get_value("MVM Employee", {"email": email, "inactive": 0})
	# Employee code, or None.
	return employee


# Zones listed on the employee record.
def get_employee_zones(employee):
	# No employee, no zones.
	if not employee:
		# Empty list.
		return []
	# Zone names of the rows in the employee's Zones table.
	return frappe.get_all(
		"MVM Employee Zone", filters={"parent": employee, "parenttype": "MVM Employee"}, pluck="zone"
	)


# Field staff see the customers they follow, that report to them, or that are in their zones.
def customer_query_conditions(user=None, doctype=None):
	# Managers see every customer.
	if is_manager(user):
		# No extra condition.
		return ""
	# Employee of the user.
	employee = get_current_employee(user)
	# A user without employee record sees nothing.
	if not employee:
		# Condition that is never true.
		return "1=0"
	# Quote the code for use in SQL.
	employee = frappe.db.escape(employee)
	# Followed by the employee, reporting to the employee, or in one of their zones.
	return f"""(`tabMVM Customer`.followed_by = {employee}
		or `tabMVM Customer`.reporting_to = {employee}
		or `tabMVM Customer`.zone in (
			select zone from `tabMVM Employee Zone`
			where parent = {employee} and parenttype = 'MVM Employee'))"""


# Same rule as customer_query_conditions, for a single customer that is opened.
def customer_has_permission(doc, ptype=None, user=None):
	# Managers may do everything; anyone with the role may create.
	if is_manager(user) or ptype == "create":
		# Allowed.
		return True
	# Employee of the user.
	employee = get_current_employee(user)
	# A user without employee record sees nothing.
	if not employee:
		# Not allowed.
		return False
	# Allowed for followed, reporting and same-zone customers.
	return employee in (doc.followed_by, doc.reporting_to) or doc.zone in get_employee_zones(employee)


# Field staff see only their own visits.
def visit_query_conditions(user=None, doctype=None):
	# Managers see every visit.
	if is_manager(user):
		# No extra condition.
		return ""
	# Employee of the user.
	employee = get_current_employee(user)
	# A user without employee record sees nothing.
	if not employee:
		# Condition that is never true.
		return "1=0"
	# Only the visits of this employee.
	return f"`tabMVM Visit Entry`.employee = {frappe.db.escape(employee)}"


# Same rule as visit_query_conditions, for a single visit that is opened.
def visit_has_permission(doc, ptype=None, user=None):
	# Managers may do everything; anyone with the role may create.
	if is_manager(user) or ptype == "create":
		# Allowed.
		return True
	# Employee of the user.
	employee = get_current_employee(user)
	# Allowed only for the employee's own visit.
	return bool(employee) and doc.employee == employee
