# File: weekly_report.py
# Purpose: Weekly email report of the visits: every employee gets their own visits, managers get their team,
#          and the people named in MVM Settings (else the admins) get all employees.
#          Sent every Monday morning for the previous Monday to Sunday (hooks.py scheduler_events),
#          only when "Send Weekly Report" is ticked in MVM Settings.
#          Summary, points to note, and every visit with customer, reason, check-in and check-out time.
# Created: 2026-10-10
# Last updated: 2026-10-12

# Splitting the list of addresses in the settings.
import re

# Frappe framework.
import frappe
# Translation function for messages shown to the user.
from frappe import _
# Date and text helpers.
from frappe.utils import add_days, cint, cstr, escape_html, formatdate, getdate, today

# Time of day as HH:MM, and working days of a period.
from my_visit_monitor.api import clock, count_working_days
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


# Button in MVM Settings: last week's report to the logged-in admin (or to `email` when given).
# Without `employee` it is the report of everybody; with it that employee's own report, or the team's with `team`.
@frappe.whitelist(methods=["POST"])
def send_test_report(email=None, employee=None, team=0):
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
	# Everybody by default.
	members = None
	# One employee was asked for.
	if employee:
		# The employee with the team, or the employee alone.
		members = get_team(employee) if cint(team) else [employee]
	# The report, to this address only.
	send_report(email, start, end, members)
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


# Email address -> employees they get: None for everybody, a manager's team, or a single employee.
# An address gets one email only: everybody wins over the team, the team wins over the own report.
def recipients():
	# Address -> members.
	result = {}
	# The addresses named in MVM Settings for the report of all employees.
	named = [
		address.lower()
		for address in re.split(r"[\s,;]+", cstr(frappe.db.get_single_value("MVM Settings", "weekly_report_all_recipients")))
		if "@" in address
	]
	# Some are named.
	for address in named:
		# Everybody's visits.
		result[address] = None
	# Nobody is named: every admin login gets all employees.
	if not named:
		# Logins that hold an admin role.
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
			# Everybody's visits.
			result[row.email.lower()] = None
	# Active employees with their address: the login's email, else the email on the employee record.
	# Employees ticked "Leave Out of Weekly Report" get no report of their own and are in nobody's team.
	employees = frappe.db.sql(
		"""
		select employee.name, lower(trim(ifnull(nullif(login.email, ''), employee.email))) as email
		from `tabMVM Employee` employee
		left join `tabUser` login on login.name = employee.user and login.enabled = 1
		where employee.inactive = 0 and employee.exclude_from_weekly_report = 0
		order by employee.name
		""",
		as_dict=True,
	)
	# Codes of the active employees.
	active = {employee.name for employee in employees}
	# Managers first, so that their team report wins over their own.
	for employee in employees:
		# The employee and the active employees reporting to them.
		team = [code for code in get_team(employee.name) if code in active]
		# No address, nobody reports to them, or they get everybody anyway.
		if not employee.email or len(team) < 2 or employee.email in result:
			# Not a manager's report.
			continue
		# The manager and the team.
		result[employee.email] = team
	# Then every employee who gets nothing yet.
	for employee in employees:
		# No address, or already a recipient.
		if not employee.email or employee.email in result:
			# Skip this employee.
			continue
		# Only their own visits.
		result[employee.email] = [employee.name]
	# Address -> members.
	return result


# Build the report for `members` (None = everybody) and queue the email to `email`.
def send_report(email, start, end, members):
	# Employee rows of the report, each with its visits.
	rows = report_rows(start, end, members)
	# "5 Oct - 11 Oct 2026"
	period = f"{formatdate(start, 'd MMM')} - {formatdate(end, 'd MMM yyyy')}"
	# Queue the email; the report is in the body, no attachment.
	frappe.sendmail(
		recipients=[email],
		subject=_("Weekly Visit Report: {0}").format(period),
		message=report_html(period, rows, start, end, members),
	)


# One dict per employee: name, manager, days worked and every visit of the week.
def report_rows(start, end, members):
	# Employees ticked "Leave Out of Weekly Report" (office and support accounts): never listed.
	left_out = set(frappe.get_all("MVM Employee", filters={"exclude_from_weekly_report": 1}, pluck="name"))
	# The employees in the report: the given ones, or every active employee.
	codes = list(members) if members is not None else frappe.get_all("MVM Employee", filters={"inactive": 0}, pluck="name")
	# Without the ones that are left out.
	codes = [code for code in codes if code not in left_out]
	# Values for the query; an empty group gets a code that cannot exist.
	values = {"start": start, "end": end, "codes": tuple(codes or [""]), "left_out": tuple(left_out or [""])}
	# Everybody: no employee filter, so inactive employees who still have visits that week are listed too.
	condition = (
		"and ifnull(visit.employee, '') != '' and visit.employee not in %(left_out)s"
		if members is None
		else "and visit.employee in %(codes)s"
	)
	# Every visit of the week, oldest first.
	visits = frappe.db.sql(
		f"""
		select visit.employee, visit.checkin_date, visit.checkin_time, visit.checkout_date, visit.checkout_time,
			visit.status, visit.checkin_location_status, visit.checkout_location_status,
			ifnull(nullif(visit.customer_name, ''), visit.customer) as customer,
			ifnull(nullif(reason.description, ''), visit.visit_reason) as reason
		from `tabMVM Visit Entry` visit
		left join `tabMVM Visit Reason` reason on reason.name = visit.visit_reason
		where visit.checkin_date between %(start)s and %(end)s {condition}
		order by visit.checkin_date, visit.checkin_time, visit.name
		""",
		values,
		as_dict=True,
	)
	# Employee -> visits of that employee.
	by_employee = {}
	# Every visit.
	for visit in visits:
		# Add the visit to its employee.
		by_employee.setdefault(visit.employee, []).append(visit)
	# Employees with visits who are not in the list yet (inactive ones, in the report of everybody).
	codes = list(dict.fromkeys([*codes, *by_employee]))
	# Code -> name and manager of every employee.
	employees = {
		row.name: row for row in frappe.get_all("MVM Employee", fields=["name", "employee_name", "reporting_to"])
	}
	# Rows of the report.
	rows = []
	# Every employee.
	for code in codes:
		# Visits of that employee.
		own = by_employee.get(code, [])
		# Employee record (name and manager).
		employee = employees.get(code) or frappe._dict()
		# The manager's record; nothing for someone who reports to nobody or to themselves.
		manager = employees.get(employee.reporting_to) if employee.reporting_to not in (None, "", code) else None
		# One row.
		rows.append(
			frappe._dict(
				code=code,
				name=employee.employee_name or code,
				manager=manager.employee_name if manager else "",
				# Days from Monday to Friday with at least one visit.
				days=len({visit.checkin_date for visit in own if visit.checkin_date.weekday() < 5}),
				visits=own,
				# Different customers visited.
				customers={cstr(visit.customer) for visit in own if visit.customer},
				# Visits still checked in.
				open_visits=sum(1 for visit in own if visit.status == "Checked In"),
				# Visits with the check-in or the check-out outside the geofence.
				outside=sum(1 for visit in own if "Outside" in (visit.checkin_location_status, visit.checkout_location_status)),
			)
		)
	# Most visits first, then by name.
	rows.sort(key=lambda row: (-len(row.visits), row.name))
	# Rows of the report.
	return rows


# -- email layout (inline styles: email programs ignore style sheets; greys only, like the Frappe desk)

# Text, muted text, line and heading background.
TEXT, MUTED, LINE, SHADE = "#1f272e", "#687178", "#d1d8dd", "#f4f5f6"
# Style of a table.
TABLE = f"width:100%;border-collapse:collapse;border:1px solid {LINE};margin:0 0 20px 0"
# Style of a table cell.
CELL = f"padding:7px 10px;border:1px solid {LINE};vertical-align:top;font-size:13px;color:{TEXT}"
# Style of a table heading cell.
HEAD = f"padding:7px 10px;border:1px solid {LINE};background:{SHADE};font-size:12px;font-weight:bold;color:{TEXT}"
# Style of a section heading.
TITLE = f"font-size:14px;font-weight:bold;color:{TEXT};margin:0 0 8px 0"


# A table from heading labels and lines of cells; `aligns` holds "left" or "center" per column.
def table(labels, lines, aligns):
	# Heading cells.
	head = "".join(f'<th style="{HEAD};text-align:{align}">{_(label)}</th>' for label, align in zip(labels, aligns))
	# Body lines; the cells are HTML already.
	body = "".join(
		"<tr>" + "".join(f'<td style="{CELL};text-align:{align}">{cell}</td>' for cell, align in zip(line, aligns)) + "</tr>"
		for line in lines
	)
	# The table.
	return f'<table style="{TABLE}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


# The lines of the visit table of one employee.
def visit_lines(visits):
	# Lines of the table.
	lines = []
	# Every visit, oldest first.
	for visit in visits:
		# Check-out time; with the date when the check-out was on a later day.
		checkout = clock(visit.checkout_time)
		# Checked out on another day.
		if checkout and visit.checkout_date and visit.checkout_date != visit.checkin_date:
			# "17 Oct 14:43"
			checkout = f"{formatdate(visit.checkout_date, 'd MMM')} {checkout}"
		# Things to remark on.
		remarks = []
		# Still checked in.
		if visit.status == "Checked In":
			# Say so.
			remarks.append(_("Not checked out"))
		# Check-in away from the customer.
		if visit.checkin_location_status == "Outside":
			# Say so.
			remarks.append(_("Check-in outside geofence"))
		# Check-out away from the customer.
		if visit.checkout_location_status == "Outside":
			# Say so.
			remarks.append(_("Check-out outside geofence"))
		# The reason in normal writing ("SALES PLANNING" -> "Sales Planning").
		reason = cstr(visit.reason)
		# One line.
		lines.append(
			[
				formatdate(visit.checkin_date, "EEE, d MMM"),
				escape_html(cstr(visit.customer)) or "-",
				escape_html(reason.title() if reason.isupper() else reason) or "-",
				clock(visit.checkin_time) or "-",
				checkout or "-",
				escape_html(", ".join(remarks)),
			]
		)
	# Lines of the table.
	return lines


# The email body: heading, summary, points to note, one line per employee, and every visit.
def report_html(period, rows, start, end, members):
	# The report of one employee about their own visits.
	own = members is not None and len(members) == 1
	# Mon to Fri in the week.
	working_days = count_working_days(start, end)
	# Employees with at least one visit.
	active = [row for row in rows if row.visits]
	# Total visits.
	total_visits = sum(len(row.visits) for row in rows)
	# Different customers visited by anybody in the report.
	total_customers = len({name for row in rows for name in row.customers})
	# Visits not checked out.
	total_open = sum(row.open_visits for row in rows)
	# Visits outside the geofence.
	total_outside = sum(row.outside for row in rows)

	# Whose visits the report covers.
	if own:
		# The employee.
		scope = f"{rows[0].name} ({rows[0].code})" if rows else ""
	# A manager's team, or everybody.
	else:
		# Team or all.
		scope = _("All employees") if members is None else _("Your team")

	# Summary: one column per figure.
	figures = [(_("Total Visits"), total_visits), (_("Customers Visited"), total_customers)]
	# Own report: days worked.
	if own:
		# "4 of 5"
		figures.append((_("Days Worked"), _("{0} of {1}").format(rows[0].days if rows else 0, working_days)))
	# Team or all: how many employees had visits.
	else:
		# "9 of 14"
		figures.append((_("Employees with Visits"), _("{0} of {1}").format(len(active), len(rows))))
	# Open and outside visits.
	figures += [(_("Not Checked Out"), total_open), (_("Outside Geofence"), total_outside)]
	# The summary table: labels on top, figures under them.
	summary = table(
		[label for label, value in figures],
		[[f'<span style="font-size:16px;font-weight:bold">{value}</span>' for label, value in figures]],
		["center"] * len(figures),
	)

	# Points to note (team and all only).
	points = []
	# Not for a single employee.
	if not own:
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
			points.append(_("Visits on fewer than half of the working days: {0}").format(", ".join(low)))
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
	# The list of points, when there are any.
	notes = ""
	# Some points.
	if points:
		# Heading and one line per point.
		notes = (
			f'<div style="{TITLE}">{_("Points to Note")}</div>'
			f'<ul style="margin:0 0 20px 0;padding-left:20px;font-size:13px;color:{TEXT}">'
			+ "".join(f'<li style="margin:3px 0">{escape_html(point)}</li>' for point in points)
			+ "</ul>"
		)

	# One line per employee (team and all only).
	overview = ""
	# Not for a single employee.
	if not own:
		# Columns; "Reports To" only where several teams are listed.
		labels = ["Employee", "Reports To", "Days Worked", "Visits", "Customers", "Not Checked Out", "Outside Geofence"]
		# Lines of the table.
		lines = [
			[
				f'{escape_html(row.name)} <span style="color:{MUTED}">({escape_html(row.code)})</span>',
				escape_html(row.manager) or "-",
				f"{row.days} / {working_days}",
				len(row.visits),
				len(row.customers),
				row.open_visits,
				row.outside,
			]
			for row in rows
		]
		# A team report has one manager: leave the column out.
		if members is not None:
			# Drop "Reports To".
			labels, lines = [labels[0], *labels[2:]], [[line[0], *line[2:]] for line in lines]
		# Heading and table.
		overview = f'<div style="{TITLE}">{_("Summary by Employee")}</div>' + table(
			labels, lines, ["left", *(["left"] if members is None else []), *["center"] * 5]
		)

	# Every visit, employee by employee.
	details = f'<div style="{TITLE}">{_("Visit Details")}</div>'
	# Columns of the visit table.
	columns = ["Date", "Customer", "Reason of Visit", "Check In", "Check Out", "Remarks"]
	# Their alignment.
	aligns = ["left", "left", "left", "center", "center", "left"]
	# Employees with visits.
	for row in active:
		# Team and all: the employee's name above the table.
		if not own:
			# "Name (code) - 7 visits", or "1 visit"
			details += (
				f'<div style="font-size:13px;font-weight:bold;color:{TEXT};margin:0 0 6px 0">{escape_html(row.name)} '
				f'<span style="color:{MUTED};font-weight:normal">({escape_html(row.code)}) &middot; '
				f'{_("1 visit") if len(row.visits) == 1 else _("{0} visits").format(len(row.visits))}</span></div>'
			)
		# The visits.
		details += table(columns, visit_lines(row.visits), aligns)
	# Nobody had a visit.
	if not active:
		# Say so.
		details += f'<p style="font-size:13px;color:{MUTED};margin:0 0 20px 0">{_("No visits were recorded in this week.")}</p>'

	# The whole message.
	return f"""
	<div style="font-family:Inter,'Segoe UI',Arial,Helvetica,sans-serif;color:{TEXT};max-width:900px">
		<div style="font-size:18px;font-weight:bold;margin:0 0 4px 0">{_("Weekly Visit Report")}</div>
		<div style="font-size:13px;color:{MUTED};padding:0 0 12px 0;margin:0 0 16px 0;border-bottom:1px solid {LINE}">
			{escape_html(period)} &middot; {escape_html(scope)} &middot; {_("{0} working days (Monday to Friday)").format(working_days)}
		</div>
		<p style="font-size:13px;margin:0 0 16px 0">{_("Please find below the visit report for the week {0}.").format(escape_html(period))}</p>
		{summary}
		{notes}
		{overview}
		{details}
		<p style="color:{MUTED};font-size:11px;margin:0">
			{_("Days Worked: days from Monday to Friday with at least one visit. Not Checked Out: visits of the week that are still checked in. Outside Geofence: check-in or check-out farther from the customer than the allowed distance. This is an automatic email from My Visit Monitor.")}
		</p>
	</div>
	"""
