# File: api.py
# Purpose: Server methods called from the forms and pages: customer search, Magic customer import, Visit Dashboard figures.
# Created: 2026-10-05
# Last updated: 2026-10-09

# Frappe framework.
import frappe
# Translation function for messages shown to the user.
from frappe import _
# Date helpers (add_days, add_months, get_last_day, getdate, today) and conversions (cint, cstr).
from frappe.utils import add_days, add_months, cint, cstr, get_last_day, getdate, today

# Who the logged-in employee is and which zones they cover.
from my_visit_monitor.permission import get_current_employee, get_employee_zones, is_manager


# Callable from the browser.
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def customer_query(doctype, txt, searchfield, start, page_len, filters):
	"""Customers an employee can log a visit for: active ones in the employee's zones."""
	# Inactive customers are never offered.
	conditions = {"inactive": 0}
	# Managers see every customer; field staff only their zones.
	if not is_manager():
		# Zones of the logged-in employee.
		zones = get_employee_zones(get_current_employee())
		# No zones means no customers.
		if not zones:
			# Empty result.
			return []
		# Limit the search to those zones.
		conditions["zone"] = ["in", zones]

	# No text filter by default.
	or_filters = None
	# Something was typed in the customer field.
	if txt:
		# Match the text anywhere.
		like = f"%{txt}%"
		# Search in the code, the company name and the contact name.
		or_filters = {"name": ["like", like], "company_name": ["like", like], "customer_name": ["like", like]}

	# Return the matching customers as code, company name, zone.
	return frappe.get_all(
		"MVM Customer",
		filters=conditions,
		or_filters=or_filters,
		fields=["name", "company_name", "zone"],
		order_by="company_name asc",
		limit_start=cint(start),
		limit_page_length=cint(page_len),
		as_list=True,
	)


# Column positions in the customer sheet exported from Magic.
MAGIC_COLUMNS = {
	"magic_code": 0,
	"code": 1,
	"company_name": 2,
	"address_line_1": 3,
	"address_line_2": 4,
	"address_line_3": 5,
	"city": 6,
	"pincode": 7,
	"state": 8,
	"country": 9,
	"zone": 10,
	"followed_by": 11,
	"reporting_to": 13,
}
# Next follow-up (days) given to every customer imported from Magic.
MAGIC_FOLLOWUP_DAYS = 15


# Callable from the browser, by POST only.
@frappe.whitelist(methods=["POST"])
def import_magic_customers(file_url, skip_header=1):
	"""Create customers from a Magic customer sheet (.xlsx). Existing customer codes are skipped."""
	# Only managers may import.
	frappe.only_for(("MVM Manager", "System Manager"))

	# Frappe's reader for attached .xlsx files.
	from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

	# All rows of the first sheet.
	rows = read_xlsx_file_from_attached_file(file_url=file_url) or []
	# The first row holds the column titles.
	if cint(skip_header):
		# Drop the title row.
		rows = rows[1:]

	# Magic code -> employee code, remembered so each is looked up once.
	employees = {}

	# Employee code for the value found in the sheet.
	def employee_for(value):
		"""Magic refers to employees by their Magic code."""
		# Not looked up yet.
		if value and value not in employees:
			# Find the employee by Magic code, else by employee code.
			employees[value] = frappe.db.get_value("MVM Employee", {"magic_code": value}) or (
				value if frappe.db.exists("MVM Employee", value) else None
			)
		# The employee code, or None when there is no such employee.
		return employees.get(value)

	# Counters for the result message.
	created, skipped = 0, 0
	# One sheet row = one customer.
	for row in rows:
		# Every cell as trimmed text.
		row = [cstr(cell).strip() for cell in row]
		# Pad short rows so every column exists.
		row += [""] * (max(MAGIC_COLUMNS.values()) + 1 - len(row))
		# Pick the columns by their position.
		values = {key: row[index] for key, index in MAGIC_COLUMNS.items()}

		# The customer code is the record name, not a field.
		code = values.pop("code")
		# Skip rows without code or name, and customers that already exist.
		if not code or not values["company_name"] or frappe.db.exists("MVM Customer", code):
			# Count the skipped row.
			skipped += 1
			# Go to the next row.
			continue

		# The zone of the sheet is not in the zone master yet.
		if values["zone"] and not frappe.db.exists("MVM Zone", values["zone"]):
			# Create that zone.
			frappe.get_doc({"doctype": "MVM Zone", "zone_name": values["zone"]}).insert(ignore_permissions=True)

		# New, empty customer.
		customer = frappe.new_doc("MVM Customer")
		# Fill in the values of the sheet.
		customer.update(values)
		# Replace the Magic code by the employee code.
		customer.followed_by = employee_for(values["followed_by"])
		# Same for the reporting manager.
		customer.reporting_to = employee_for(values["reporting_to"])
		# Default follow-up interval.
		customer.next_followup_days = MAGIC_FOLLOWUP_DAYS
		# the sheet has no mobile and may refer to employees that do not exist here yet
		customer.insert(set_name=code, ignore_mandatory=True, ignore_permissions=True)
		# Count the created customer.
		created += 1

	# Show the result to the user.
	frappe.msgprint(_("Imported {0} customers, skipped {1} rows.").format(created, skipped))
	# Result for the caller.
	return {"created": created, "skipped": skipped}


# Longest period the Visit Dashboard may ask for, in days (a leap year).
DASHBOARD_MAX_DAYS = 366
# Months shown in the visits-per-month chart.
DASHBOARD_TREND_MONTHS = 12
# Most customers listed under "not visited".
DASHBOARD_MISSED_LIMIT = 100
# Number of rows in a "top" list.
DASHBOARD_TOP_LIMIT = 10


# Everything the Visit Dashboard page shows for one employee and one period.
# A day counts as worked when the employee checked in to at least one visit on it.
@frappe.whitelist()
def get_dashboard(employee=None, start=None, end=None):
	"""Return attendance, work figures, charts and, for managers, the comparison of all employees."""
	# Managers may look at any employee.
	manager = is_manager()
	# Field staff always get their own record; a manager gets it when no employee was chosen.
	if not manager or not employee:
		# Employee of the logged-in user; None when there is none.
		employee = get_current_employee()
	# A chosen employee must exist.
	elif not frappe.db.exists("MVM Employee", employee):
		# Stop with a message.
		frappe.throw(_("Employee {0} does not exist.").format(employee))

	# Today.
	current = getdate(today())
	# First day of the period; this month when none was given.
	start = getdate(start) if start else current.replace(day=1)
	# Last day of the period; the end of that month when none was given.
	end = getdate(end) if end else get_last_day(start)
	# The period must run forwards and be at most a year long.
	if end < start or (end - start).days >= DASHBOARD_MAX_DAYS:
		# Stop with a message.
		frappe.throw(_("Invalid period."))

	# What the page always gets.
	data = {
		"employee": employee,
		"employee_name": frappe.db.get_value("MVM Employee", employee, "employee_name") if employee else None,
		"is_manager": manager,
		"today": today(),
		"start": str(start),
		"end": str(end),
		# Monday to Friday in the period, up to today.
		"working_days": count_working_days(start, min(end, current)),
	}
	# The figures of the chosen employee.
	if employee:
		# Add them to the answer.
		data.update(employee_dashboard(employee, start, end))
	# Only managers see the other employees.
	if manager:
		# Add the comparison of all employees.
		data["team"] = team_dashboard(start, end)
		# Add the customers visited most by all employees together.
		data["team_top_customers"] = top_customers(start, end)
	# Answer for the page.
	return data


# Number of Mondays to Fridays from `start` to `end`, both included.
def count_working_days(start, end):
	# Days counted so far.
	count = 0
	# Day being looked at.
	day = start
	# Every day of the range.
	while day <= end:
		# Monday is 0, Friday is 4.
		if day.weekday() < 5:
			# A working day.
			count += 1
		# Next day.
		day = add_days(day, 1)
	# Number of working days.
	return count


# Work figures per employee for a period: {employee: {visits, days_worked, ...}}.
# With `employee` only that employee is worked out; without it every employee is.
def performance(start, end, employee=None):
	# Extra condition when only one employee is wanted (fixed text, the value goes in separately).
	condition = "and employee = %(employee)s" if employee else ""
	# Values for the queries.
	values = {"start": start, "end": end, "employee": employee}
	# Employee -> figures.
	result = {}

	# Figures of one employee, created empty the first time it is asked for.
	def figures(code):
		# All counters start at zero.
		return result.setdefault(
			code,
			{"visits": 0, "days_worked": 0, "weekdays_worked": 0, "customers": 0, "allocated": 0, "covered": 0},
		)

	# One row per employee and day with visits.
	rows = frappe.db.sql(
		f"""
		select employee, checkin_date, count(*) as visits
		from `tabMVM Visit Entry`
		where checkin_date between %(start)s and %(end)s and ifnull(employee, '') != '' {condition}
		group by employee, checkin_date
		""",
		values,
		as_dict=True,
	)
	# Add the days up per employee.
	for row in rows:
		# Figures of that employee.
		item = figures(row.employee)
		# Visits of that day.
		item["visits"] += row.visits
		# One more day worked.
		item["days_worked"] += 1
		# Monday to Friday.
		if row.checkin_date.weekday() < 5:
			# One more working day worked.
			item["weekdays_worked"] += 1

	# Employee -> customers visited in the period.
	visited = {}
	# One row per employee and customer.
	pairs = frappe.db.sql(
		f"""
		select distinct employee, customer
		from `tabMVM Visit Entry`
		where checkin_date between %(start)s and %(end)s and ifnull(employee, '') != '' {condition}
		""",
		values,
	)
	# Collect the customers per employee.
	for code, customer in pairs:
		# Add the customer to the set of that employee.
		visited.setdefault(code, set()).add(customer)

	# Employee -> zones of that employee.
	zones = {}
	# One row per employee and zone.
	for code, zone in frappe.db.sql("select parent, zone from `tabMVM Employee Zone` where parenttype = 'MVM Employee'"):
		# Add the zone to the set of that employee.
		zones.setdefault(code, set()).add(zone)
	# Code, zone and follower of every active customer.
	customers = frappe.db.sql("select name, zone, followed_by from `tabMVM Customer` where inactive = 0")

	# The one employee, or every active employee.
	employees = [employee] if employee else frappe.get_all("MVM Employee", filters={"inactive": 0}, pluck="name")
	# Also employees who are inactive now but have visits in the period.
	for code in set(employees) | set(result):
		# Figures of that employee.
		item = figures(code)
		# Customers that employee visited.
		seen = visited.get(code, set())
		# Customers allocated to the employee: followed by them, or in one of their zones.
		allocated = {
			name
			for name, zone, followed_by in customers
			if followed_by == code or (zone and zone in zones.get(code, ()))
		}
		# Different customers visited.
		item["customers"] = len(seen)
		# Customers allocated.
		item["allocated"] = len(allocated)
		# Allocated customers that were visited.
		item["covered"] = len(allocated & seen)
		# Allocated customers that were not visited.
		item["missed"] = allocated - seen
	# Figures per employee.
	return result


# Calendar, charts and lists of one employee for the period.
def employee_dashboard(employee, start, end):
	# Work figures of the employee.
	summary = performance(start, end, employee)[employee]
	# Allocated customers that were not visited; taken out because a set cannot be sent to the page.
	missed = summary.pop("missed")
	# Values for the queries.
	values = {"employee": employee, "start": start, "end": end}

	# Date (YYYY-MM-DD) -> what happened on that day.
	days = {}
	# One row per day with visits.
	rows = frappe.db.sql(
		"""
		select checkin_date, count(*) as visits, count(distinct customer) as customers,
			min(checkin_time) as first_in, max(checkout_time) as last_out
		from `tabMVM Visit Entry`
		where employee = %(employee)s and checkin_date between %(start)s and %(end)s
		group by checkin_date
		""",
		values,
		as_dict=True,
	)
	# Turn the rows into the per-day dictionary.
	for row in rows:
		# Counts and times of that day.
		days[str(row.checkin_date)] = {
			"visits": row.visits,
			"customers": row.customers,
			"first_in": clock(row.first_in),
			"last_out": clock(row.last_out),
			# Names of the customers visited; filled below.
			"customer_names": [],
		}

	# One row per day and customer visited on it; the code is used when the visit has no name.
	pairs = frappe.db.sql(
		"""
		select distinct checkin_date, ifnull(nullif(customer_name, ''), customer) as customer
		from `tabMVM Visit Entry`
		where employee = %(employee)s and checkin_date between %(start)s and %(end)s
		order by checkin_date, customer
		""",
		values,
	)
	# Put every name with its day.
	for date, customer in pairs:
		# Visits without any customer are left out.
		if customer:
			# The days come from the same visits, so the day is always there.
			days[str(date)]["customer_names"].append(customer)

	# First day of the chart: the month 11 months before the month the period ends in.
	trend_start = add_months(end.replace(day=1), 1 - DASHBOARD_TREND_MONTHS)
	# Month (YYYY-MM) -> visits and days worked in that month.
	trend = {}
	# One row per month with visits.
	rows = frappe.db.sql(
		"""
		select date_format(checkin_date, '%%Y-%%m') as month, count(*) as visits,
			count(distinct checkin_date) as days_worked
		from `tabMVM Visit Entry`
		where employee = %(employee)s and checkin_date between %(start)s and %(end)s
		group by month
		""",
		{"employee": employee, "start": trend_start, "end": get_last_day(end)},
		as_dict=True,
	)
	# Remember the months that have visits.
	for row in rows:
		# Visits and days worked of that month.
		trend[row.month] = {"visits": row.visits, "days_worked": row.days_worked}
	# All 12 months in order, also the ones without visits.
	months = []
	# Month 0 is the oldest.
	for offset in range(DASHBOARD_TREND_MONTHS):
		# Month as YYYY-MM.
		month = str(add_months(trend_start, offset))[:7]
		# The month with its figures; zero when there were no visits.
		months.append({"month": month, **trend.get(month, {"visits": 0, "days_worked": 0})})

	# Visits per reason, most used first.
	reasons = frappe.db.sql(
		"""
		select ifnull(reason.description, visit.visit_reason) as reason, count(*) as visits
		from `tabMVM Visit Entry` visit
		left join `tabMVM Visit Reason` reason on reason.name = visit.visit_reason
		where visit.employee = %(employee)s and visit.checkin_date between %(start)s and %(end)s
		group by visit.visit_reason, reason.description
		order by visits desc
		""",
		values,
		as_dict=True,
	)

	# Customers whose first visit by this employee falls in the period.
	new_customers = frappe.db.sql(
		"""
		select count(*) from (
			select customer from `tabMVM Visit Entry`
			where employee = %(employee)s and ifnull(customer, '') != ''
			group by customer
			having min(checkin_date) between %(start)s and %(end)s
		) first_visits
		""",
		values,
	)[0][0]

	# Allocated customers without a visit in the period.
	not_visited = []
	# Only look them up when there are any.
	if missed:
		# Customer -> date of the last visit by this employee, ever.
		last_visits = dict(
			frappe.db.sql(
				"select customer, max(checkin_date) from `tabMVM Visit Entry` where employee = %s group by customer",
				employee,
			)
		)
		# Name, city and zone of those customers.
		rows = frappe.get_all(
			"MVM Customer",
			filters={"name": ["in", list(missed)]},
			fields=["name", "company_name", "city", "zone"],
		)
		# Add the last visit to every customer.
		for row in rows:
			# Date as text; empty when the employee never visited the customer.
			row["last_visit"] = str(last_visits.get(row.name) or "")
		# Never visited first, then the longest ago.
		rows.sort(key=lambda row: (row.last_visit, row.company_name or ""))
		# The page shows only the first ones.
		not_visited = rows[:DASHBOARD_MISSED_LIMIT]

	# Everything about the employee.
	return {
		"summary": summary,
		"days": days,
		"trend": months,
		"reasons": reasons,
		"new_customers": new_customers,
		# The customers this employee visited most.
		"top_customers": top_customers(start, end, employee),
		"not_visited": not_visited,
		"not_visited_count": len(missed),
	}


# The customers with the most visits in the period: of one employee, or of all employees together.
def top_customers(start, end, employee=None):
	# Extra condition when only one employee is wanted (fixed text, the value goes in separately).
	condition = "and employee = %(employee)s" if employee else ""
	# One row per customer, most visits first.
	rows = frappe.db.sql(
		f"""
		select customer, max(ifnull(nullif(customer_name, ''), customer)) as customer_name,
			count(*) as visits, count(distinct checkin_date) as days,
			count(distinct employee) as employees, max(checkin_date) as last_visit
		from `tabMVM Visit Entry`
		where checkin_date between %(start)s and %(end)s and ifnull(customer, '') != '' {condition}
		group by customer
		order by visits desc, customer_name
		limit {DASHBOARD_TOP_LIMIT}
		""",
		{"start": start, "end": end, "employee": employee},
		as_dict=True,
	)
	# Dates are sent to the page as text.
	for row in rows:
		# Date of the last visit as YYYY-MM-DD.
		row["last_visit"] = str(row.last_visit or "")
	# Rows for the top 10 table.
	return rows


# Work figures of every employee for the period, the one with the most visits first.
def team_dashboard(start, end):
	# Code -> name of every employee.
	names = dict(frappe.db.sql("select name, employee_name from `tabMVM Employee`"))
	# One row per employee.
	team = []
	# Figures of all employees.
	for code, item in performance(start, end).items():
		# The set of missed customers is not needed here and cannot be sent to the page.
		item.pop("missed")
		# The figures with the code and the name of the employee.
		team.append({"employee": code, "employee_name": names.get(code) or code, **item})
	# Most visits first; the name decides between equals.
	team.sort(key=lambda row: (-row["visits"], row["employee_name"]))
	# Rows for the comparison table.
	return team


# A time of day as HH:MM; an empty text when there is none.
def clock(value):
	# No check-in or check-out time.
	if value is None:
		# Nothing to show.
		return ""
	# The database returns a time as the duration since midnight.
	if hasattr(value, "total_seconds"):
		# Whole seconds since midnight.
		seconds = int(value.total_seconds())
		# Hours and minutes.
		return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"
	# Already a time or a text like 09:05:00.
	return str(value)[:5]
