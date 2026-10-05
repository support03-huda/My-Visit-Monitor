import frappe
from frappe import _
from frappe.utils import cint, cstr

from my_visit_monitor.permission import get_current_employee, get_employee_zones, is_manager


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def customer_query(doctype, txt, searchfield, start, page_len, filters):
	"""Customers an employee can log a visit for: active ones in the employee's zones."""
	conditions = {"inactive": 0}
	if not is_manager():
		zones = get_employee_zones(get_current_employee())
		if not zones:
			return []
		conditions["zone"] = ["in", zones]

	or_filters = None
	if txt:
		like = f"%{txt}%"
		or_filters = {"name": ["like", like], "company_name": ["like", like], "customer_name": ["like", like]}

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
MAGIC_FOLLOWUP_DAYS = 15


@frappe.whitelist(methods=["POST"])
def import_magic_customers(file_url, skip_header=1):
	"""Create customers from a Magic customer sheet (.xlsx). Existing customer codes are skipped."""
	frappe.only_for(("MVM Manager", "System Manager"))

	from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

	rows = read_xlsx_file_from_attached_file(file_url=file_url) or []
	if cint(skip_header):
		rows = rows[1:]

	employees = {}

	def employee_for(value):
		"""Magic refers to employees by their Magic code."""
		if value and value not in employees:
			employees[value] = frappe.db.get_value("MVM Employee", {"magic_code": value}) or (
				value if frappe.db.exists("MVM Employee", value) else None
			)
		return employees.get(value)

	created, skipped = 0, 0
	for row in rows:
		row = [cstr(cell).strip() for cell in row]
		row += [""] * (max(MAGIC_COLUMNS.values()) + 1 - len(row))
		values = {key: row[index] for key, index in MAGIC_COLUMNS.items()}

		code = values.pop("code")
		if not code or not values["company_name"] or frappe.db.exists("MVM Customer", code):
			skipped += 1
			continue

		if values["zone"] and not frappe.db.exists("MVM Zone", values["zone"]):
			frappe.get_doc({"doctype": "MVM Zone", "zone_name": values["zone"]}).insert(ignore_permissions=True)

		customer = frappe.new_doc("MVM Customer")
		customer.update(values)
		customer.followed_by = employee_for(values["followed_by"])
		customer.reporting_to = employee_for(values["reporting_to"])
		customer.next_followup_days = MAGIC_FOLLOWUP_DAYS
		# the sheet has no mobile and may refer to employees that do not exist here yet
		customer.insert(set_name=code, ignore_mandatory=True, ignore_permissions=True)
		created += 1

	frappe.msgprint(_("Imported {0} customers, skipped {1} rows.").format(created, skipped))
	return {"created": created, "skipped": skipped}
