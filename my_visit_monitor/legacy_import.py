"""Bring the data of the old MyVisitMonitor (ScriptCase / MySQL) database into this app.

bench --site <site> execute my_visit_monitor.legacy_import.run --kwargs "{'path': '<dump.sql>'}"

The old codes are kept as they are: customers, employees, locations and visit reasons keep
their code as name, visits keep their visit number.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, get_datetime, now

from my_visit_monitor.sql_dump import parse_inserts

# children and dependants first, so that clearing never leaves a dangling row
DOCTYPES = [
	"MVM Visit Entry",
	"MVM Customer",
	"MVM Employee Zone",
	"MVM Employee",
	"MVM Visit Reason",
	"MVM Location",
	"MVM Zone",
]
VISIT_SERIES = "MVM-VISIT"
ADMIN_GROUP = 1


def run(path, clear_existing=0, create_users=1):
	"""Import a dump that is on the server."""
	with open(path, encoding="utf-8", errors="replace") as dump:
		return import_dump(dump.read(), clear_existing, create_users)


@frappe.whitelist(methods=["POST"])
def import_from_file(file_url, clear_existing=0, create_users=1):
	"""Import a dump uploaded to the site."""
	frappe.only_for("System Manager")
	content = frappe.get_doc("File", {"file_url": file_url}).get_content()
	if isinstance(content, bytes):
		content = content.decode("utf-8", errors="replace")
	return import_dump(content, clear_existing, create_users)


def import_dump(text, clear_existing=0, create_users=1):
	tables = parse_inserts(text)
	if not tables.get("customermst") and not tables.get("visitentry"):
		frappe.throw(_("This file does not look like a MyVisitMonitor database dump."))

	existing = [doctype for doctype in DOCTYPES if frappe.db.count(doctype)]
	if existing and not cint(clear_existing):
		frappe.throw(
			_("{0} already has records. Import again with 'Delete existing records first' to replace them.").format(
				", ".join(existing)
			)
		)
	for doctype in existing:
		frappe.db.delete(doctype)

	importer = LegacyImporter(tables)
	counts = importer.run(cint(create_users))
	summary = ", ".join(f"{label}: {count}" for label, count in counts.items())
	frappe.msgprint(_("Imported {0}").format(summary))
	print(summary)
	return counts


class LegacyImporter:
	def __init__(self, tables):
		self.tables = tables
		self.employees = {row["employee_code"]: row for row in self.rows("employeemst")}
		self.customers = {row["customer_code"]: row for row in self.rows("customermst")}
		self.reasons = {row["visitreason_code"] for row in self.rows("visitreasonmst")}
		self.zones = [cstr(row["zone_desc"]).strip() for row in self.rows("zonemst") if row["zone_desc"]]
		self.users = {}

	def rows(self, table):
		return self.tables.get(table) or []

	def run(self, create_users):
		counts = {}
		if create_users:
			counts["Users"] = self.import_users()
		# employee code -> login, used for the owner of the imported records
		self.users = {
			code: row["employee_emailid"]
			for code, row in self.employees.items()
			if row["employee_emailid"] and frappe.db.exists("User", row["employee_emailid"])
		}
		counts["Zones"] = self.import_zones()
		counts["Locations"] = self.import_locations()
		counts["Visit Reasons"] = self.import_reasons()
		counts["Employees"] = self.import_employees()
		counts["Customers"] = self.import_customers()
		counts["Visits"] = self.import_visits()
		return counts

	# -- helpers

	def insert(self, doctype, name, row, by_employee=False, **values):
		doc = frappe.new_doc(doctype)
		doc.update(values)
		doc.name = name
		# only visits recorded who made them; the masters carry a fixed placeholder code
		doc.owner = (by_employee and self.users.get(row.get("created_by"))) or "Administrator"
		doc.modified_by = (by_employee and self.users.get(row.get("modified_by"))) or doc.owner
		doc.creation = timestamp(row.get("created_on"), row.get("created_time"))
		doc.modified = timestamp(row.get("modified_on"), row.get("modified_time"), doc.creation)
		# written as it was: the old data does not pass today's mandatory and link checks
		doc.db_insert()
		doc.set_parent_in_children()
		for child in doc.get_all_children():
			child.owner, child.creation, child.modified = doc.owner, doc.creation, doc.modified
			child.db_insert()
		return 1

	def zone(self, value):
		"""The old columns were 5 characters wide, so '(Blank)' is stored as '(Blan'."""
		value = cstr(value).strip()
		if not value or value in self.zones:
			return value or None
		return next((zone for zone in self.zones if zone.startswith(value)), None)

	def employee(self, code):
		return code if code in self.employees else None

	# -- masters

	def import_users(self):
		admins = {row["login"] for row in self.rows("sec_users_groups") if cint(row["group_id"]) == ADMIN_GROUP}
		count = 0
		for row in self.rows("sec_users"):
			email = cstr(row["email"]).strip().lower()
			if not email:
				continue
			role = "MVM Manager" if row["priv_admin"] == "Y" or row["login"] in admins else "MVM User"
			if frappe.db.exists("User", email):
				user = frappe.get_doc("User", email)
			else:
				user = frappe.new_doc("User")
				user.update(
					{
						"email": email,
						"first_name": row["name"] or email,
						"enabled": cint(row["active"] == "Y"),
						# passwords cannot be carried over and nobody should get a mail from an import
						"send_welcome_email": 0,
					}
				)
				user.flags.no_welcome_mail = True
				user.insert(ignore_permissions=True)
				count += 1
			user.add_roles(role)
		return count

	def import_zones(self):
		wanted = list(self.zones)
		for row in self.rows("customermst"):
			zone = cstr(row["customer_zone"]).strip()
			if zone and zone not in wanted:
				wanted.append(zone)
		self.zones = wanted
		return sum(self.insert("MVM Zone", zone, {}, zone_name=zone) for zone in wanted)

	def import_locations(self):
		return sum(
			self.insert(
				"MVM Location",
				row["location_code"],
				row,
				location_name=row["location_name"],
				mobile=row["location_mobile"],
				email=row["location_emailid"],
				magic_code=row["location_magic_code"],
				digipin=row["location_digipin"],
				inactive=cint(row["location_inactive"] == "Y"),
				pincode=row["location_pincode"],
				city=row["location_city"],
				state=row["location_state"],
				country=row["location_country"],
				**address(row, "location"),
			)
			for row in self.rows("locationmst")
		)

	def import_reasons(self):
		return sum(
			self.insert(
				"MVM Visit Reason",
				row["visitreason_code"],
				row,
				description=row["visitreason_description"],
				inactive=cint(row["visitreason_inactive"] == "Y"),
			)
			for row in self.rows("visitreasonmst")
		)

	def import_employees(self):
		zones = {}
		for row in self.rows("employee_zonemst"):
			zone = self.zone(row["zone_code"])
			if zone and zone not in zones.setdefault(row["employee_code"], []):
				zones[row["employee_code"]].append(zone)

		count = 0
		for code, row in self.employees.items():
			count += self.insert(
				"MVM Employee",
				code,
				row,
				employee_name=row["employee_name"],
				email=row["employee_emailid"],
				user=self.users.get(code),
				mobile=row["employee_mobile"],
				location=row["employee_location"],
				reporting_to=self.employee(row["employee_reporting_to"]),
				inactive=cint(row["employee_inactive"] == "Y"),
				city=row["employee_city"],
				state=row["employee_state"],
				country=row["employee_country"],
				magic_code=row["employee_magic_code"],
				payroll_magic_code=row.get("employee_payrool_magic_code"),
				digipin=row["employee_digipin"],
				zones=[{"zone": zone} for zone in zones.get(code, [])],
				**address(row, "employee"),
			)
		return count

	def import_customers(self):
		return sum(
			self.insert(
				"MVM Customer",
				code,
				row,
				company_name=row["customer_company_name"],
				customer_name=row["customer_name"],
				mobile=row["customer_mobile"],
				email=row["customer_emailid"],
				# codes of people who are not in the employee master are left out
				followed_by=self.employee(row["customer_followed_by"]),
				reporting_to=self.employee(row["customer_reporting_to"]),
				zone=self.zone(row["customer_zone"]),
				next_followup_days=cint(row["customer_next_followup"]),
				inactive=cint(row["customer_inactive"] == "Y"),
				pincode=row["customer_pincode"],
				city=row["customer_city"],
				state=row["customer_state"],
				country=row["customer_country"],
				magic_code=row["customer_magic_code"],
				digipin=row["customer_digipin"],
				**address(row, "customer"),
			)
			for code, row in self.customers.items()
		)

	# -- visits

	def import_visits(self):
		count, last_number, company_id = 0, 0, None
		for row in self.rows("visitentry"):
			number = cstr(row["visit_number"])
			customer = self.customers.get(row["visit_customer_code"])
			employee = self.employees.get(row["visit_employee_code"])
			values = {
				"customer": customer and customer["customer_code"],
				"customer_name": customer and customer["customer_company_name"],
				"visit_reason": row["visited_for"] if row["visited_for"] in self.reasons else None,
				"description": row["visit_description"],
				"employee": employee and employee["employee_code"],
				"employee_name": employee and employee["employee_name"],
				"status": "Checked Out" if row["visit_date_out"] else "Checked In",
				"digipin": row["visit_digipin"],
				"checkin_date": row["visit_date_in"],
				"checkin_time": row["visit_time_in"],
				"checkin_latitude": flt(row["visit_browser_latitude_in"]),
				"checkin_longitude": flt(row["visit_browser_longitude_in"]),
				"checkout_date": row["visit_date_out"],
				"checkout_time": row["visit_time_out"],
				"checkout_latitude": flt(row["visit_browser_latitude_out"]),
				"checkout_longitude": flt(row["visit_browser_longitude_out"]),
				"customer_latitude": flt(row["visit_map_latitude_in"]),
				"customer_longitude": flt(row["visit_map_longitude_in"]),
			}
			# the old app always stored the visit date here, which says nothing
			if row["next_visit_date"] != row["visit_date_in"]:
				values["next_visit_date"] = row["next_visit_date"]
			count += self.insert("MVM Visit Entry", number, row, by_employee=True, **values)

			if cint(number[-6:]) >= last_number:
				last_number, company_id = cint(number[-6:]), number[2:4]

		self.continue_visit_numbers(last_number, company_id)
		return count

	def continue_visit_numbers(self, last_number, company_id):
		"""New visits carry on from the last old visit number."""
		for row in self.rows("documentmst"):
			if row["document_name"] == "Visits":
				last_number = max(last_number, cint(row["document_last_number"]))
		frappe.db.delete("Series", {"name": VISIT_SERIES})
		frappe.db.sql("insert into `tabSeries` (`name`, `current`) values (%s, %s)", (VISIT_SERIES, last_number))
		if company_id:
			frappe.db.set_single_value("MVM Settings", "company_id", company_id)


def address(row, prefix):
	"""The old column names differ per table: `x_address_line_1` or `x_address _line_1`."""
	lines = {}
	for number in (1, 2, 3):
		lines[f"address_line_{number}"] = row.get(f"{prefix}_address_line_{number}") or row.get(
			f"{prefix}_address _line_{number}"
		)
	return lines


def timestamp(date, time, default=None):
	try:
		return get_datetime(f"{date} {time}")
	except Exception:
		return default or now()
