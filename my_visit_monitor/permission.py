import frappe

MANAGER_ROLES = {"MVM Manager", "System Manager"}


def is_manager(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or bool(MANAGER_ROLES.intersection(frappe.get_roles(user)))


def get_current_employee(user=None):
	"""Code of the active MVM Employee linked to the user, if any."""
	user = user or frappe.session.user
	employee = frappe.db.get_value("MVM Employee", {"user": user, "inactive": 0})
	if not employee:
		# the employee may have been created before the user existed, so User was never filled
		email = frappe.db.get_value("User", user, "email")
		employee = email and frappe.db.get_value("MVM Employee", {"email": email, "inactive": 0})
	return employee


def get_employee_zones(employee):
	if not employee:
		return []
	return frappe.get_all(
		"MVM Employee Zone", filters={"parent": employee, "parenttype": "MVM Employee"}, pluck="zone"
	)


# Field staff see the customers they follow, that report to them, or that are in their zones.
def customer_query_conditions(user=None, doctype=None):
	if is_manager(user):
		return ""
	employee = get_current_employee(user)
	if not employee:
		return "1=0"
	employee = frappe.db.escape(employee)
	return f"""(`tabMVM Customer`.followed_by = {employee}
		or `tabMVM Customer`.reporting_to = {employee}
		or `tabMVM Customer`.zone in (
			select zone from `tabMVM Employee Zone`
			where parent = {employee} and parenttype = 'MVM Employee'))"""


def customer_has_permission(doc, ptype=None, user=None):
	if is_manager(user) or ptype == "create":
		return True
	employee = get_current_employee(user)
	if not employee:
		return False
	return employee in (doc.followed_by, doc.reporting_to) or doc.zone in get_employee_zones(employee)


# Field staff see only their own visits.
def visit_query_conditions(user=None, doctype=None):
	if is_manager(user):
		return ""
	employee = get_current_employee(user)
	if not employee:
		return "1=0"
	return f"`tabMVM Visit Entry`.employee = {frappe.db.escape(employee)}"


def visit_has_permission(doc, ptype=None, user=None):
	if is_manager(user) or ptype == "create":
		return True
	employee = get_current_employee(user)
	return bool(employee) and doc.employee == employee
