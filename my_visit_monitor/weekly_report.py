# File: weekly_report.py
# Purpose: Weekly email report of the employees' visits: managers get their team, admins get everybody.
#          Sent every Monday morning for the previous Monday to Sunday (hooks.py scheduler_events),
#          only when "Send Weekly Report" is ticked in MVM Settings.
#          Summary boxes, points that need attention, and per employee every customer visited (no attachment).
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
	# "5 Oct - 11 Oct 2026"
	period = f"{formatdate(start, 'd MMM')} - {formatdate(end, 'd MMM yyyy')}"
	# Queue the email; the report is in the body, no attachment.
	frappe.sendmail(
		recipients=[email],
		subject=_("Weekly Visit Report: {0}").format(period),
		message=report_html(period, rows, start, end, members is None),
	)


# One dict per employee: name, manager, attendance, visits, every customer visited, open and outside visits.
def report_rows(start, end, members):
	# Visits, days worked and customers per employee.
	figures = performance(start, end)
	# The employees in the report: the team, or every active employee.
	codes = members if members is not None else frappe.get_all("MVM Employee", filters={"inactive": 0}, pluck="name")
	# Inactive employees who still have visits that week are listed too (admins only).
	if members is None:
		# Add them.
		codes = list(dict.fromkeys([*codes, *[code for code, item in figures.items() if item["visits"]]]))
	# Values for the queries; an empty group gets a code that cannot exist.
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
	# Employee -> customers visited that week: [(name, visits)], most visits first.
	customers = {}
	# Visits per employee and customer.
	for code, name, visits in frappe.db.sql(
		"""
		select employee, max(ifnull(nullif(customer_name, ''), customer)), count(*) as visits
		from `tabMVM Visit Entry`
		where checkin_date between %(start)s and %(end)s and employee in %(codes)s and ifnull(customer, '') != ''
		group by employee, customer
		order by employee, visits desc, 2
		""",
		values,
	):
		# Add the customer to that employee's list.
		customers.setdefault(code, []).append((cstr(name), cint(visits)))
	# Employee -> names of the customers that employee visited for the first time ever this week.
	new_customers = {}
	# First visit per employee and customer, only those that fall in the week.
	for code, name in frappe.db.sql(
		"""
		select employee, max(ifnull(nullif(customer_name, ''), customer))
		from `tabMVM Visit Entry`
		where employee in %(codes)s and ifnull(customer, '') != ''
		group by employee, customer
		having min(checkin_date) between %(start)s and %(end)s
		""",
		values,
	):
		# Remember the name.
		new_customers.setdefault(code, set()).add(cstr(name))
	# Code -> name and manager of the employees in the report.
	employees = {
		row.name: row
		for row in frappe.get_all(
			"MVM Employee", filters={"name": ["in", codes or [""]]}, fields=["name", "employee_name", "reporting_to"]
		)
	}
	# Code -> name of every employee, for the manager's name.
	names = dict(frappe.get_all("MVM Employee", fields=["name", "employee_name"], as_list=True))
	# Rows of the report.
	rows = []
	# Every employee.
	for code in codes:
		# Figures of that employee; zeros when there were no visits.
		item = figures.get(code) or {}
		# Open and outside counts of that employee.
		extra = counts.get(code) or {}
		# Employee record (name and manager).
		employee = employees.get(code) or frappe._dict()
		# One row.
		rows.append(
			frappe._dict(
				code=code,
				name=employee.employee_name or code,
				# The manager's name; empty for someone who reports to nobody or to themselves.
				manager=names.get(employee.reporting_to) if employee.reporting_to not in (None, "", code) else "",
				days=cint(item.get("weekdays_worked")),
				visits=cint(item.get("visits")),
				customers=customers.get(code, []),
				new_customers=new_customers.get(code, set()),
				open_visits=cint(extra.get("open_visits")),
				outside=cint(extra.get("outside")),
			)
		)
	# Most visits first, then by name.
	rows.sort(key=lambda row: (-row.visits, row.name))
	# Rows of the report.
	return rows


# -- email layout (inline styles: email programs ignore style sheets)

# Colours of the email.
BLUE, GREEN, RED, AMBER, GREY, LINE = "#1f4e79", "#2f9e44", "#e03131", "#e67700", "#6b7280", "#e5e7eb"
# Style of a table cell.
CELL = f"padding:10px 12px;border-bottom:1px solid {LINE};vertical-align:top;font-size:13px"


# A number box of the summary row.
def tile(label, value, colour=BLUE):
	# Big number with a small label under it.
	return (
		f'<td style="padding:6px"><div style="border:1px solid {LINE};border-radius:8px;padding:12px;text-align:center;background:#fafafa">'
		f'<div style="font-size:24px;font-weight:bold;color:{colour}">{value}</div>'
		f'<div style="font-size:12px;color:{GREY};margin-top:2px">{escape_html(label)}</div></div></td>'
	)


# A number that turns red when it is not zero.
def flag(value, colour=RED):
	# Zero in grey, anything else bold and coloured.
	return f'<span style="color:{colour};font-weight:bold">{value}</span>' if value else f'<span style="color:{GREY}">0</span>'


# The email body: heading, summary boxes, points that need attention, and one line per employee.
def report_html(period, rows, start, end, everybody):
	# Mon to Fri in the week.
	working_days = count_working_days(start, end)
	# Employees with at least one visit.
	active = [row for row in rows if row.visits]
	# Every customer visited by anybody in the report.
	all_customers = {name for row in rows for name, visits in row.customers}
	# Total visits.
	total_visits = sum(row.visits for row in rows)
	# Visits not checked out.
	total_open = sum(row.open_visits for row in rows)
	# Visits outside the geofence.
	total_outside = sum(row.outside for row in rows)
	# Customers visited for the first time.
	total_new = sum(len(row.new_customers) for row in rows)

	# Summary boxes.
	tiles = "".join(
		[
			tile(_("Total Visits"), total_visits),
			tile(_("Customers Visited"), len(all_customers)),
			tile(_("New Customers"), total_new, GREEN),
			tile(_("Employees Active"), f"{len(active)}/{len(rows)}"),
			tile(_("Not Checked Out"), total_open, RED if total_open else GREY),
			tile(_("Outside Geofence"), total_outside, RED if total_outside else GREY),
		]
	)

	# Points that need attention.
	points = []
	# Employees without a single visit.
	idle = [row.name for row in rows if not row.visits]
	# Some had none.
	if idle:
		# Name them.
		points.append(_("No visits this week: {0}").format(", ".join(idle)))
	# Employees who worked on fewer than half of the working days.
	low = [f"{row.name} ({row.days}/{working_days})" for row in active if row.days * 2 < working_days]
	# Some did.
	if low:
		# Name them.
		points.append(_("Worked on fewer than half of the working days: {0}").format(", ".join(low)))
	# Visits left open.
	opened = [f"{row.name} ({row.open_visits})" for row in rows if row.open_visits]
	# Some are.
	if opened:
		# Name them.
		points.append(_("Visits not checked out: {0}").format(", ".join(opened)))
	# Visits away from the customer.
	away = [f"{row.name} ({row.outside})" for row in rows if row.outside]
	# Some are.
	if away:
		# Name them.
		points.append(_("Check-in or check-out outside the geofence: {0}").format(", ".join(away)))
	# The attention box, or a short all-good line.
	if points:
		# Amber box with one line per point.
		attention = (
			f'<div style="background:#fff8e6;border:1px solid #f5d38a;border-radius:8px;padding:12px 16px;margin:16px 0">'
			f'<div style="font-weight:bold;color:{AMBER};margin-bottom:6px">{_("Needs attention")}</div>'
			+ "".join(f'<div style="font-size:13px;margin:4px 0">&bull; {escape_html(point)}</div>' for point in points)
			+ "</div>"
		)
	# Nothing to point out.
	else:
		# Green line.
		attention = (
			f'<div style="background:#ebfbee;border:1px solid #b2f2bb;border-radius:8px;padding:12px 16px;margin:16px 0;color:{GREEN}">'
			f'{_("Everybody worked, and all visits were checked out and inside the geofence.")}</div>'
		)

	# One table line per employee.
	lines = []
	# Every employee.
	for row in rows:
		# Attendance as a share of the working days.
		percent = round(row.days * 100 / working_days) if working_days else 0
		# Green from 80 %, amber from 50 %, else red.
		colour = GREEN if percent >= 80 else AMBER if percent >= 50 else RED
		# Every customer, with its number of visits when more than one, and "NEW" for a first visit.
		names = "<br>".join(
			escape_html(name)
			+ (f' <span style="color:{GREY}">({visits})</span>' if visits > 1 else "")
			+ (
				f' <span style="background:{GREEN};color:#fff;border-radius:4px;padding:0 4px;font-size:10px">{_("NEW")}</span>'
				if name in row.new_customers
				else ""
			)
			for name, visits in row.customers
		) or f'<span style="color:{GREY}">-</span>'
		# Manager under the name, in the admins' report where all teams are listed.
		manager = (
			f'<div style="color:{GREY};font-size:11px">{_("Reports to")} {escape_html(row.manager)}</div>'
			if everybody and row.manager
			else ""
		)
		# The line.
		lines.append(
			f"""<tr>
				<td style="{CELL}"><b>{escape_html(row.name)}</b> <span style="color:{GREY};font-size:11px">{escape_html(row.code)}</span>{manager}</td>
				<td style="{CELL};text-align:center"><span style="color:{colour};font-weight:bold">{row.days}/{working_days}</span><div style="color:{GREY};font-size:11px">{percent}%</div></td>
				<td style="{CELL};text-align:center;font-weight:bold">{row.visits}</td>
				<td style="{CELL}"><div style="font-weight:bold;margin-bottom:4px">{len(row.customers)}</div>{names}</td>
				<td style="{CELL};text-align:center">{flag(row.open_visits)}</td>
				<td style="{CELL};text-align:center">{flag(row.outside)}</td>
			</tr>"""
		)
	# Heading cells of the table.
	head = "".join(
		f'<th style="padding:10px 12px;background:{BLUE};color:#fff;font-size:12px;text-align:{align}">{_(label)}</th>'
		for label, align in [
			("Employee", "left"),
			("Days Worked", "center"),
			("Visits", "center"),
			("Customers Visited", "left"),
			("Not Checked Out", "center"),
			("Outside Geofence", "center"),
		]
	)
	# Who the report covers.
	scope = _("All employees") if everybody else _("Your team")

	# The whole message.
	return f"""
	<div style="font-family:Arial,Helvetica,sans-serif;color:#1f2937;max-width:900px">
		<div style="background:{BLUE};color:#fff;border-radius:8px 8px 0 0;padding:16px 20px">
			<div style="font-size:20px;font-weight:bold">{_("Weekly Visit Report")}</div>
			<div style="font-size:13px;margin-top:4px">{escape_html(period)} &middot; {scope} &middot; {_("{0} working days (Mon-Fri)").format(working_days)}</div>
		</div>
		<table style="width:100%;border-collapse:collapse;margin-top:8px"><tr>{tiles}</tr></table>
		{attention}
		<table style="width:100%;border-collapse:collapse;border:1px solid {LINE}">
			<thead><tr>{head}</tr></thead>
			<tbody>{"".join(lines)}</tbody>
		</table>
		<p style="color:{GREY};font-size:11px;margin-top:12px">
			{_("Days Worked: days from Monday to Friday with at least one visit. (2) after a customer: number of visits. NEW: first visit ever by this employee. Not Checked Out: visits of the week still checked in. Outside Geofence: check-in or check-out farther from the customer than the geofence radius.")}
		</p>
	</div>
	"""
