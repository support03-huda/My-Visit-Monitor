# File: api.py
# Purpose: Server methods called from the forms: customer search and the Magic customer import.
# Created: 2026-10-05
# Last updated: 2026-10-07

# Frappe framework.
import frappe
# Translation function for messages shown to the user.
from frappe import _
# cint: to whole number, cstr: to text.
from frappe.utils import cint, cstr

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
