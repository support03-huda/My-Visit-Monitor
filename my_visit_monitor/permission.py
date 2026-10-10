# File: permission.py
# Purpose: Who may see which customers and visits. Registered in hooks.py.
#          Admin (MVM Manager / System Manager) sees everything. A team manager (an employee others report to)
#          sees their own team. Every other employee sees only their own work.
# Created: 2026-10-05
# Last updated: 2026-10-10

# Frappe framework.
import frappe

# Users with one of these roles see everything ("admin").
MANAGER_ROLES = {"MVM Manager", "System Manager"}
# Role of a team manager ("manager"), given on approval; managers see their team.
TEAM_MANAGER_ROLE = "MVM Team Manager"


# True for Administrator and for users with an admin role.
def is_manager(user=None):
	# Default to the logged-in user.
	user = user or frappe.session.user
	# Administrator, or a user holding an admin role.
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


# The employee and everyone whose "Reporting To" is this employee.
def get_team(employee):
	# No employee, no team.
	if not employee:
		# Empty list.
		return []
	# Employees reporting to this one; the employee itself is added in front.
	members = frappe.get_all(
		"MVM Employee", filters={"reporting_to": employee, "name": ["!=", employee]}, pluck="name"
	)
	# The employee first, then the team members.
	return [employee, *members]


# True for a team manager: the Manager role, or others report to the employee of the user (Ishwar, Shirish).
def is_team_manager(user=None):
	# Default to the logged-in user.
	user = user or frappe.session.user
	# Holds the Manager role.
	if TEAM_MANAGER_ROLE in frappe.get_roles(user):
		# A manager.
		return True
	# Employee of the user.
	employee = get_current_employee(user)
	# At least one other employee reports to them.
	return bool(employee) and len(get_team(employee)) > 1


# Employees whose work the user may see: None means everybody (admin), else a list of codes.
def get_visible_employees(user=None):
	# Admins see everybody.
	if is_manager(user):
		# No limit.
		return None
	# The user's own employee and their team; an empty list when the user has no employee record.
	return get_team(get_current_employee(user))


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


# A list of codes as SQL text: ('A00001', 'S00004').
def sql_list(codes):
	# Every code quoted, separated by commas.
	return "(" + ", ".join(frappe.db.escape(code) for code in codes) + ")"


# Employees see the customers followed by, reporting to, or in a zone of someone in their team
# (just themselves for field staff).
def customer_query_conditions(user=None, doctype=None):
	# Whose customers the user may see.
	team = get_visible_employees(user)
	# Admins see every customer.
	if team is None:
		# No extra condition.
		return ""
	# A user without employee record sees nothing.
	if not team:
		# Condition that is never true.
		return "1=0"
	# The team as SQL text.
	codes = sql_list(team)
	# Followed by the team, reporting to the team, or in one of the team's zones.
	return f"""(`tabMVM Customer`.followed_by in {codes}
		or `tabMVM Customer`.reporting_to in {codes}
		or `tabMVM Customer`.zone in (
			select zone from `tabMVM Employee Zone`
			where parent in {codes} and parenttype = 'MVM Employee'))"""


# Same rule as customer_query_conditions, for a single customer that is opened.
def customer_has_permission(doc, ptype=None, user=None):
	# Anyone with the role may create a customer.
	if ptype == "create":
		# Allowed.
		return True
	# Whose customers the user may see.
	team = get_visible_employees(user)
	# Admins may do everything.
	if team is None:
		# Allowed.
		return True
	# Followed by or reporting to someone in the team.
	if doc.followed_by in team or doc.reporting_to in team:
		# Allowed.
		return True
	# In a zone of someone in the team.
	return any(doc.zone in get_employee_zones(member) for member in team)


# Employee records: admins see all, a manager the team, an employee only their own record.
def employee_query_conditions(user=None, doctype=None):
	# Whose records the user may see.
	team = get_visible_employees(user)
	# Admins see every employee.
	if team is None:
		# No extra condition.
		return ""
	# A user without employee record sees none.
	if not team:
		# Condition that is never true.
		return "1=0"
	# Only the team.
	return f"`tabMVM Employee`.name in {sql_list(team)}"


# Same rule for a single employee record; everyone except admins may change only their own record.
def employee_has_permission(doc, ptype=None, user=None):
	# Whose records the user may see.
	team = get_visible_employees(user)
	# Admins may do everything.
	if team is None:
		# Allowed.
		return True
	# Reading: the team.
	if ptype in (None, "read", "print", "email", "report", "export"):
		# Allowed for the team.
		return doc.name in team
	# Creating, deleting and changing other records is for admins only; one's own record may be changed.
	return ptype == "write" and bool(team) and doc.name == team[0]


# Employees see the visits of their team (just their own for field staff).
def visit_query_conditions(user=None, doctype=None):
	# Whose visits the user may see.
	team = get_visible_employees(user)
	# Admins see every visit.
	if team is None:
		# No extra condition.
		return ""
	# A user without employee record sees nothing.
	if not team:
		# Condition that is never true.
		return "1=0"
	# Only the visits of the team.
	return f"`tabMVM Visit Entry`.employee in {sql_list(team)}"


# Same rule as visit_query_conditions, for a single visit that is opened.
def visit_has_permission(doc, ptype=None, user=None):
	# Anyone with the role may create a visit (it is always their own).
	if ptype == "create":
		# Allowed.
		return True
	# Whose visits the user may see.
	team = get_visible_employees(user)
	# Admins may do everything.
	if team is None:
		# Allowed.
		return True
	# Reading: a team manager may look at the visits of the whole team.
	if ptype in (None, "read", "print", "email", "report", "export"):
		# Allowed for visits of the team.
		return doc.employee in team
	# Changing (check out): only the employee's own visit.
	return bool(team) and doc.employee == team[0]
