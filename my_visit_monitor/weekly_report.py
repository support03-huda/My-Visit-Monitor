# File: weekly_report.py
# Purpose: Weekly email report of the employees' visits: managers get their team, admins get everybody.
#          Sent every Monday morning for the previous Monday to Sunday (hooks.py scheduler_events),
#          only when "Send Weekly Report" is ticked in MVM Settings.
# Created: 2026-10-10
# Last updated: 2026-10-10

# Frappe framework.
import frappe
# Translation function for messages shown to the user.
from frappe import _
# Date helpers.
from frappe.utils import add_days, cint, cstr, escape_html, formatdate, getdate, today

# Work figures per employee (visits, days worked, customers).
from my_visit_monitor.api import count_working_days, performance
# Admin check and team of a manager.
from my_visit_monitor.permission import MANAGER_ROLES, get_team, is_manager
# Whether an outgoing email account is set up.
from my_visit_monitor.my_visit_monitor.doctype.mvm_registration.mvm_registration import has_outgoing_email

# Customers named per employee in the report.
TOP_CUSTOMERS_PER_EMPLOYEE = 3
# Column headings of the report table (also the first row of the Excel file).
HEADINGS = [
	"Employee",
	"Code",
	"Days Worked (Mon-Fri)",
	"Visits",
	"Customers",
	"Not Checked Out",
	"Outside Geofence",
	"Top Customers",
]


# Scheduler entry point (Monday morning): send the report of last week when it is switched on.
def send_weekly_reports():
	# Switched off in MVM Settings (the default, so a test site never mails anybody).
	if not cint(frappe.db.get_single_value("MVM Settings", "weekly_report_enabled")):
		# Nothing to do.
		return
	# No email account to send with.
	if not has_outgoing_email():
		# Leave a note in the Error Log.
		frappe.log_error(title="MVM weekly report not sent", message="No default outgoing Email Account.")
		# Nothing more to do.
		return
	# Monday to Sunday of last week.
	start, end = last_week()
	# Every recipient with the employees they get.
	for email, members in recipients().items():
		# One email per recipient; a failure is logged and the others still get theirs.
		try:
			# Build and queue the email.
			send_report(email, start, end, members)
		# Something went wrong for this recipient.
		except Exception:
			# Keep a record in the Error Log.
			frappe.log_error(title=f"MVM weekly report to {email} failed")


# Button in MVM Settings: last week's report of everybody, to the logged-in admin (or to `email` when given).
@frappe.whitelist(methods=["POST"])
def send_test_report(email=None):
	# Only admins.
	if not is_manager():
		# Stop with a message.
		frappe.throw(_("Only an administrator can send the test report."), frappe.PermissionError)
	# No email account to send with.
	if not has_outgoing_email():
		# Stop with a message.
		frappe.throw(_("Please set up a default outgoing Email Account first."))
	# Monday to Sunday of last week.
	start, end = last_week()
	# The address asked for, else the email address of the logged-in user.
	email = cstr(email).strip() or frappe.db.get_value("User", frappe.session.user, "email")
	# Everybody's figures, to this user only.
	send_report(email, start, end, None)
	# Tell the user where it went.
	return email


# Monday and Sunday of the week before this one.
def last_week():
	# Today.
	current = getdate(today())
	# Last Sunday: on a Monday that is yesterday.
	end = add_days(current, -(current.weekday() + 1))
	# The Monday before it.
	return getdate(add_days(end, -6)), getdate(end)


# Email address -> employees they get: None for admins (everybody), else a manager's team.
def recipients():
	# Address -> members.
	result = {}
	# Enabled logins that hold an admin role.
	admins = frappe.get_all(
		"Has Role",
		filters={"role": ["in", list(MANAGER_ROLES)], "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	# Every admin login.
	for user in admins:
		# Login details.
		row = frappe.db.get_value("User", user, ["enabled", "email", "user_type"], as_dict=True)
		# Disabled, website-only or built-in users get nothing.
		if not row or not row.enabled or row.user_type != "System User" or user in ("Administrator", "Guest"):
			# Skip this login.
			continue
		# Everybody's figures.
		result[row.email.lower()] = None
	# Active employees others report to (Ishwar, Shirish, Solomon).
	managers = frappe.db.sql(
		"""
		select distinct manager.name, manager.email, manager.user
		from `tabMVM Employee` manager
		join `tabMVM Employee` member on member.reporting_to = manager.name and member.name != manager.name
		where manager.inactive = 0 and member.inactive = 0
		""",
		as_dict=True,
	)
	# Every manager.
	for manager in managers:
		# The login's email, else the email on the employee record (managers may not have a login yet).
		email = cstr(frappe.db.get_value("User", manager.user, "email") if manager.user else manager.email).strip().lower()
		# No address, or an admin who gets everybody anyway.
		if not email or email in result:
			# Skip this manager.
			continue
		# The manager and the team.
		result[email] = get_team(manager.name)
	# Address -> members.
	return result


# Build the report for `members` (None = everybody) and queue the email to `email`.
def send_report(email, start, end, members):
	# Employee rows of the report.
	rows = report_rows(start, end, members)
	# "6 Oct - 12 Oct 2026"
	period = f"{formatdate(start, 'd MMM')} - {formatdate(end, 'd MMM yyyy')}"
	# Subject line.
	subject = _("Weekly Visit Report: {0}").format(period)
	# Excel file with the same table.
	from frappe.utils.xlsxutils import make_xlsx

	# Heading row first, then the employees.
	xlsx = make_xlsx([HEADINGS, *rows], "Weekly Report").getvalue()
	# Queue the email with the table and the Excel attachment.
	frappe.sendmail(
		recipients=[email],
		subject=subject,
		message=report_html(period, rows, start, end, members is None),
		attachments=[{"fname": f"weekly-visit-report_{start}_{end}.xlsx", "fcontent": xlsx}],
	)


# One row per employee: name, code, days worked, visits, customers, open visits, outside geofence, top customers.
def report_rows(start, end, members):
	# Visits, days worked and customers per employee.
	figures = performance(start, end)
	# The employees in the report: the team, or every active employee.
	codes = members if members is not None else frappe.get_all("MVM Employee", filters={"inactive": 0}, pluck="name")
	# Inactive employees who still have visits that week are listed too (admins only).
	if members is None:
		# Add them.
		codes = list(dict.fromkeys([*codes, *[code for code, item in figures.items() if item["visits"]]]))
	# Values for the queries.
	values = {"start": start, "end": end, "codes": tuple(codes or [""])}
	# Employee -> visits still checked in, and visits outside the geofence.
	counts = {
		row.employee: row
		for row in frappe.db.sql(
			"""
			select employee,
				sum(status = 'Checked In') as open_visits,
				sum(checkin_location_status = 'Outside' or checkout_location_status = 'Outside') as outside
			from `tabMVM Visit Entry`
			where checkin_date between %(start)s and %(end)s and employee in %(codes)s
			group by employee
			""",
			values,
			as_dict=True,
		)
	}
	# Employee -> customers with the most visits that week.
	top = {}
	# Visits per employee and customer, most first.
	for code, name, visits in frappe.db.sql(
		"""
		select employee, max(ifnull(nullif(customer_name, ''), customer)), count(*) as visits
		from `tabMVM Visit Entry`
		where checkin_date between %(start)s and %(end)s and employee in %(codes)s and ifnull(customer, '') != ''
		group by employee, customer
		order by employee, visits desc
		""",
		values,
	):
		# The first few customers of each employee.
		if len(top.setdefault(code, [])) < TOP_CUSTOMERS_PER_EMPLOYEE:
			# "BHARAT FORGE LTD (3)"
			top[code].append(f"{name} ({visits})")
	# Code -> name of the employees.
	names = dict(frappe.get_all("MVM Employee", filters={"name": ["in", codes or [""]]}, fields=["name", "employee_name"], as_list=True))
	# Rows of the report.
	rows = []
	# Every employee.
	for code in codes:
		# Figures of that employee; zeros when there were no visits.
		item = figures.get(code) or {}
		# Open and outside counts of that employee.
		extra = counts.get(code) or {}
		# One row.
		rows.append(
			[
				names.get(code) or code,
				code,
				cint(item.get("weekdays_worked")),
				cint(item.get("visits")),
				cint(item.get("customers")),
				cint(extra.get("open_visits")),
				cint(extra.get("outside")),
				", ".join(top.get(code, [])),
			]
		)
	# Most visits first, then by name.
	rows.sort(key=lambda row: (-row[3], row[0]))
	# Rows of the report.
	return rows


# The email body: a short summary and the table.
def report_html(period, rows, start, end, everybody):
	# Mon to Fri in the week.
	working_days = count_working_days(start, end)
	# Totals over all employees.
	total_visits = sum(row[3] for row in rows)
	# Employees without a single visit.
	idle = [row[0] for row in rows if not row[3]]
	# Table cells; numbers aligned right.
	body = "".join(
		"<tr>"
		+ "".join(
			f'<td style="border:1px solid #ccc;padding:4px 8px;{"text-align:right;" if isinstance(cell, int) else ""}">{escape_html(cstr(cell))}</td>'
			for cell in row
		)
		+ "</tr>"
		for row in rows
	)
	# Heading cells.
	head = "".join(f'<th style="border:1px solid #ccc;padding:4px 8px;background:#f3f3f3;text-align:left">{_(h)}</th>' for h in HEADINGS)
	# Who the report covers.
	scope = _("all employees") if everybody else _("your team")
	# Employees with no visits, when there are any.
	idle_line = f"<p><b>{_('No visits')}:</b> {escape_html(', '.join(idle))}</p>" if idle else ""
	# The whole message.
	return f"""
		<p>{_("Visit report of {0} for {1}.").format(scope, escape_html(period))}</p>
		<p>{_("Working days (Mon-Fri)")}: <b>{working_days}</b> &nbsp; {_("Total visits")}: <b>{total_visits}</b></p>
		{idle_line}
		<table style="border-collapse:collapse;font-size:13px">
			<thead><tr>{head}</tr></thead>
			<tbody>{body}</tbody>
		</table>
		<p style="color:#888;font-size:12px">{_("The same table is attached as an Excel file. Not Checked Out: visits of the week that are still checked in. Outside Geofence: check-in or check-out farther from the customer than the geofence radius.")}</p>
	"""
