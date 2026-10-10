# File: legacy_import.py
# Purpose: Imports the old MyVisitMonitor MySQL database (MVM Settings > Import Old Database).
# Created: 2026-10-07
# Last updated: 2026-10-10

"""Bring the data of the old MyVisitMonitor (ScriptCase / MySQL) database into this app.

bench --site <site> execute my_visit_monitor.legacy_import.run --kwargs "{'path': '<dump.sql>'}"

With merge=1 only the records that are missing are added (a newer dump on a site that is in use):
existing records are left as they are, no logins are created and nothing is deleted.
With renumber=1 as well, a visit made in this app that has the number of an old visit gets the next free
number, and the old visit is added under its own number.

The old codes are kept as they are: customers, employees, locations and visit reasons keep
their code as name, visits keep their visit number.
"""

# Frappe framework.
import frappe
# Translation function for messages shown to the user.
from frappe import _
# Conversion and date helpers.
from frappe.utils import cint, cstr, flt, get_datetime, now

# Reader for the .sql file.
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
# Name of the running number used for visit numbers.
VISIT_SERIES = "MVM-VISIT"
# Group id of the administrators in the old security tables.
ADMIN_GROUP = 1


# Entry point for the bench command.
def run(path, clear_existing=0, create_users=1, merge=0, renumber=0):
	"""Import a dump that is on the server."""
	# Open the dump; unreadable characters are replaced.
	with open(path, encoding="utf-8", errors="replace") as dump:
		# Import its content.
		return import_dump(dump.read(), clear_existing, create_users, merge, renumber)


# Callable from the browser, by POST only.
@frappe.whitelist(methods=["POST"])
def import_from_file(file_url, clear_existing=0, create_users=1, merge=0, renumber=0):
	"""Import a dump uploaded to the site."""
	# Only a System Manager may run the import.
	frappe.only_for("System Manager")
	# Content of the uploaded file.
	content = frappe.get_doc("File", {"file_url": file_url}).get_content()
	# Files come back as bytes.
	if isinstance(content, bytes):
		# Turn the bytes into text.
		content = content.decode("utf-8", errors="replace")
	# Import that text.
	return import_dump(content, clear_existing, create_users, merge, renumber)


# Check the file, clear the existing records when asked, then import everything.
# merge=1: keep every existing record and add only what is missing.
# renumber=1 (with merge): move visits made here off the numbers of old visits.
def import_dump(text, clear_existing=0, create_users=1, merge=0, renumber=0):
	# All INSERT rows of the dump, per table.
	tables = parse_inserts(text)
	# A dump without customers and visits is not ours.
	if not tables.get("customermst") and not tables.get("visitentry"):
		# Stop with a message.
		frappe.throw(_("This file does not look like a MyVisitMonitor database dump."))

	# Doctypes that already hold records; a merge keeps them all.
	existing = [] if cint(merge) else [doctype for doctype in DOCTYPES if frappe.db.count(doctype)]
	# Records exist and deleting them was not asked for.
	if existing and not cint(clear_existing):
		# Stop with a message.
		frappe.throw(
			_("{0} already has records. Import again with 'Delete existing records first' to replace them.").format(
				", ".join(existing)
			)
		)
	# Deleting was asked for.
	for doctype in existing:
		# Remove every record of that doctype.
		frappe.db.delete(doctype)

	# Prepare the importer with the rows of the dump.
	importer = LegacyImporter(tables, merge=cint(merge), renumber=cint(merge) and cint(renumber))
	# Run the import; a merge never creates logins (people sign up and are approved).
	counts = importer.run(0 if cint(merge) else cint(create_users))
	# Text like `Users: 15, Zones: 14, ...`.
	summary = ", ".join(f"{label}: {count}" for label, count in counts.items())
	# Show it on the screen.
	frappe.msgprint(_("Imported {0}").format(summary))
	# And on the console, for the bench command.
	print(summary)
	# Counts for the caller.
	return counts


# Holds the rows of the dump and writes them into the MVM doctypes.
class LegacyImporter:
	# Index the tables that other tables refer to.
	def __init__(self, tables, merge=0, renumber=0):
		# All rows of the dump.
		self.tables = tables
		# Only add missing records.
		self.merge = merge
		# Move visits made here off the numbers of old visits.
		self.renumber = renumber
		# Employee code -> employee row.
		self.employees = {row["employee_code"]: row for row in self.rows("employeemst")}
		# Customer code -> customer row.
		self.customers = {row["customer_code"]: row for row in self.rows("customermst")}
		# Codes of the visit reasons.
		self.reasons = {row["visitreason_code"] for row in self.rows("visitreasonmst")}
		# Zone names of the zone master.
		self.zones = [cstr(row["zone_desc"]).strip() for row in self.rows("zonemst") if row["zone_desc"]]
		# Employee code -> login; filled in run().
		self.users = {}

	# Rows of one old table; an empty list when the dump does not have it.
	def rows(self, table):
		# Rows of the table.
		return self.tables.get(table) or []

	# Import in dependency order and return how many records were created.
	def run(self, create_users):
		# Label -> number of records created.
		counts = {}
		# Logins were asked for.
		if create_users:
			# Create the logins first, so employees can be linked to them.
			counts["Users"] = self.import_users()
		# employee code -> login, used for the owner of the imported records
		self.users = {
			code: row["employee_emailid"]
			for code, row in self.employees.items()
			if row["employee_emailid"] and frappe.db.exists("User", row["employee_emailid"])
		}
		# Zones first: employees and customers refer to them.
		counts["Zones"] = self.import_zones()
		# Office locations.
		counts["Locations"] = self.import_locations()
		# Visit reasons.
		counts["Visit Reasons"] = self.import_reasons()
		# Employees.
		counts["Employees"] = self.import_employees()
		# Customers.
		counts["Customers"] = self.import_customers()
		# Visits last: they refer to customers, employees and reasons.
		counts["Visits"] = self.import_visits()
		# A merge also reports open visits that were checked out in the old app since.
		if self.merge:
			# Visits whose check-out was added.
			counts["Visits Checked Out"] = self.checked_out
			# Visits made here that got a new number.
			counts["Visits Renumbered"] = len(self.renumbered)
			# Visit numbers already used by a different visit on this site.
			counts["Visit Number Conflicts"] = len(self.conflicts)
			# Old number -> new number of the moved visits, for the summary on the console.
			if self.renumbered:
				# Print them.
				print("renumbered:", ", ".join(f"{old} -> {new}" for old, new in self.renumbered))
			# Those numbers, for the summary on the console.
			if self.conflicts:
				# Print them.
				print("conflicting visit numbers:", ", ".join(self.conflicts))
		# Counts for the summary.
		return counts

	# -- helpers

	# Write one record with its old code, owner and dates.
	def insert(self, doctype, name, row, by_employee=False, **values):
		# A merge leaves an existing record as it is.
		if self.merge and frappe.db.exists(doctype, name):
			# Nothing created.
			return 0
		# New, empty record.
		doc = frappe.new_doc(doctype)
		# Fill in the field values.
		doc.update(values)
		# Keep the old code as the record name.
		doc.name = name
		# only visits recorded who made them; the masters carry a fixed placeholder code
		doc.owner = (by_employee and self.users.get(row.get("created_by"))) or "Administrator"
		# Last editor; the creator when it is unknown.
		doc.modified_by = (by_employee and self.users.get(row.get("modified_by"))) or doc.owner
		# Creation date and time of the old record.
		doc.creation = timestamp(row.get("created_on"), row.get("created_time"))
		# Last change of the old record.
		doc.modified = timestamp(row.get("modified_on"), row.get("modified_time"), doc.creation)
		# written as it was: the old data does not pass today's mandatory and link checks
		doc.db_insert()
		# Link the child rows to this record.
		doc.set_parent_in_children()
		# Child rows (the zones of an employee).
		for child in doc.get_all_children():
			# Same owner and dates as the parent.
			child.owner, child.creation, child.modified = doc.owner, doc.creation, doc.modified
			# Write the child row.
			child.db_insert()
		# One record created; the callers add these up.
		return 1

	# Full zone name for a value found in the old data.
	def zone(self, value):
		"""The old columns were 5 characters wide, so '(Blank)' is stored as '(Blan'."""
		# Trimmed text.
		value = cstr(value).strip()
		# Empty, or already a full zone name.
		if not value or value in self.zones:
			# Use it as it is; empty becomes None.
			return value or None
		# Else the zone that starts with the cut-off value.
		return next((zone for zone in self.zones if zone.startswith(value)), None)

	# The code when that employee exists in the dump, else None.
	def employee(self, code):
		# Unknown employee codes are dropped.
		return code if code in self.employees else None

	# -- masters

	# Create a login for every old user; administrators become MVM Manager.
	def import_users(self):
		# Logins that belong to the administrators group.
		admins = {row["login"] for row in self.rows("sec_users_groups") if cint(row["group_id"]) == ADMIN_GROUP}
		# Number of logins created.
		count = 0
		# Every old user.
		for row in self.rows("sec_users"):
			# The email address is the login in Frappe.
			email = cstr(row["email"]).strip().lower()
			# A user without email cannot get a login.
			if not email:
				# Skip that user.
				continue
			# Administrators become MVM Manager, everybody else MVM User.
			role = "MVM Manager" if row["priv_admin"] == "Y" or row["login"] in admins else "MVM User"
			# The login already exists on this site.
			if frappe.db.exists("User", email):
				# Use it.
				user = frappe.get_doc("User", email)
			# The login does not exist yet.
			else:
				# New, empty user.
				user = frappe.new_doc("User")
				# Fill in email, name and whether the user is enabled.
				user.update(
					{
						"email": email,
						"first_name": row["name"] or email,
						"enabled": cint(row["active"] == "Y"),
						# passwords cannot be carried over and nobody should get a mail from an import
						"send_welcome_email": 0,
					}
				)
				# Do not send the welcome mail.
				user.flags.no_welcome_mail = True
				# Create the user.
				user.insert(ignore_permissions=True)
				# Count it.
				count += 1
			# Give the role, also to a login that existed already.
			user.add_roles(role)
		# Number of logins created.
		return count

	# Zones of the zone master plus any zone that only appears on a customer.
	def import_zones(self):
		# Start with the zones of the zone master.
		wanted = list(self.zones)
		# Look at the zone of every customer.
		for row in self.rows("customermst"):
			# Zone written on the customer.
			zone = cstr(row["customer_zone"]).strip()
			# A zone that is missing from the zone master.
			if zone and zone not in wanted:
				# Add it.
				wanted.append(zone)
		# Remember the complete list for zone().
		self.zones = wanted
		# Create every zone and count them.
		return sum(self.insert("MVM Zone", zone, {}, zone_name=zone) for zone in wanted)

	# Office locations.
	def import_locations(self):
		# Create every location and count them.
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

	# Visit reasons.
	def import_reasons(self):
		# Create every reason and count them.
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

	# Employees together with their zones.
	def import_employees(self):
		# Employee code -> zones of that employee.
		zones = {}
		# Every employee / zone pair.
		for row in self.rows("employee_zonemst"):
			# Full zone name.
			zone = self.zone(row["zone_code"])
			# Known zone that is not listed for this employee yet.
			if zone and zone not in zones.setdefault(row["employee_code"], []):
				# Add it.
				zones[row["employee_code"]].append(zone)

		# Number of employees created.
		count = 0
		# Every employee.
		for code, row in self.employees.items():
			# Create the employee with its zones.
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
		# Number of employees created.
		return count

	# Customers.
	def import_customers(self):
		# Create every customer and count them.
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

	# Visits with their check-in / check-out time and position.
	def import_visits(self):
		# Visits created, highest running number and its company id.
		count, last_number, company_id = 0, 0, None
		# Merge only: open visits that got their check-out, and numbers used by another visit.
		self.checked_out, self.conflicts = 0, []
		# Renumber only: old visits waiting for their number, and the moves made (old number, new number).
		self.waiting, self.renumbered = [], []
		# Every old visit.
		for row in self.rows("visitentry"):
			# Visit number, e.g. 2603001382.
			number = cstr(row["visit_number"])
			# Customer row; None when the customer no longer exists.
			customer = self.customers.get(row["visit_customer_code"])
			# Employee row; None when the employee no longer exists.
			employee = self.employees.get(row["visit_employee_code"])
			# Field values of the visit.
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
				# Keep the next visit date only when it is a different day.
				values["next_visit_date"] = row["next_visit_date"]
			# A merge and the visit number is already on this site.
			if self.merge and frappe.db.exists("MVM Visit Entry", number):
				# Compare it with the old visit; a number taken by another visit waits when renumbering.
				if not self.merge_visit(number, values) and self.renumber:
					# Add it after the visit made here has moved.
					self.waiting.append((number, row, values))
			# A new visit.
			else:
				# Create the visit; its owner is the employee who made it.
				count += self.insert("MVM Visit Entry", number, row, by_employee=True, **values)

			# Highest running number so far (the last 6 digits).
			if cint(number[-6:]) >= last_number:
				# Remember it together with its company id (digits 3 and 4).
				last_number, company_id = cint(number[-6:]), number[2:4]

		# Renumbering: move the visits made here, then add the old visits under their own numbers.
		if self.waiting:
			# Highest number in use: the site's counter or the last old visit.
			current = max(series_current(), last_number)
			# Every old visit whose number was taken.
			for number, row, values in self.waiting:
				# Next free running number.
				current += 1
				# Same year and company id, new running number.
				new_number = f"{number[:4]}{current:06d}"
				# Move the visit made here.
				frappe.rename_doc("MVM Visit Entry", number, new_number, force=True, ignore_permissions=True, show_alert=False)
				# Remember the move.
				self.renumbered.append((number, new_number))
				# The number is free now: it is no longer a conflict.
				self.conflicts.remove(number)
				# Add the old visit.
				count += self.insert("MVM Visit Entry", number, row, by_employee=True, **values)
			# New visits continue after the moved ones.
			last_number = current
		# New visits continue after the last old one.
		self.continue_visit_numbers(last_number, company_id)
		# Number of visits created.
		return count

	# Merge: the visit number exists. Same visit: add a check-out made in the old app since. Other visit: report it.
	def merge_visit(self, number, values):
		# The visit on this site.
		current = frappe.db.get_value(
			"MVM Visit Entry", number, ["employee", "checkin_date", "status"], as_dict=True
		)
		# A different employee or day: the number was given to a visit made in this app.
		if current.employee != values["employee"] or cstr(current.checkin_date) != cstr(values["checkin_date"]):
			# Report it and leave both alone.
			self.conflicts.append(number)
			# Not the same visit.
			return False
		# Still open here but checked out in the old app.
		if current.status == "Checked In" and values["checkout_date"]:
			# Copy the check-out without running the checks of a manual save.
			frappe.db.set_value(
				"MVM Visit Entry",
				number,
				{
					"status": "Checked Out",
					"checkout_date": values["checkout_date"],
					"checkout_time": values["checkout_time"],
					"checkout_latitude": values["checkout_latitude"],
					"checkout_longitude": values["checkout_longitude"],
				},
				update_modified=False,
			)
			# Count it.
			self.checked_out += 1
		# The same visit.
		return True

	# Set the running number and the company id for new visits.
	def continue_visit_numbers(self, last_number, company_id):
		"""New visits carry on from the last old visit number."""
		# A merge never lowers the counter: visits made here may have used higher numbers.
		if self.merge:
			# Current counter of this site.
			current = series_current()
			# Keep the higher one.
			last_number = max(cint(current), cint(last_number))
		# The old app kept its own counter table.
		for row in self.rows("documentmst"):
			# The counter of the visits.
			if row["document_name"] == "Visits":
				# Use it when it is higher.
				last_number = max(last_number, cint(row["document_last_number"]))
		# Remove the current counter.
		frappe.db.delete("Series", {"name": VISIT_SERIES})
		# Store the new counter.
		frappe.db.sql("insert into `tabSeries` (`name`, `current`) values (%s, %s)", (VISIT_SERIES, last_number))
		# The old visit numbers carried a company id.
		if company_id:
			# Use the same company id for new visits.
			frappe.db.set_single_value("MVM Settings", "company_id", company_id)


# Current value of the visit counter; 0 when there is none.
def series_current():
	"""Plain SQL: tabSeries has no creation column, which get_value orders by."""
	# The counter row.
	rows = frappe.db.sql("select current from `tabSeries` where name = %s", VISIT_SERIES)
	# Its value, or 0.
	return cint(rows[0][0]) if rows else 0


# The three address lines of an old row.
def address(row, prefix):
	"""The old column names differ per table: `x_address_line_1` or `x_address _line_1`."""
	# Field name -> value.
	lines = {}
	# Address line 1, 2 and 3.
	for number in (1, 2, 3):
		# Try both spellings of the old column name.
		lines[f"address_line_{number}"] = row.get(f"{prefix}_address_line_{number}") or row.get(
			f"{prefix}_address _line_{number}"
		)
	# The address fields.
	return lines


# Date and time of the old record as one value; `default` or now when they are invalid.
def timestamp(date, time, default=None):
	# The date or time may be empty or invalid.
	try:
		# Date and time as one value.
		return get_datetime(f"{date} {time}")
	# Invalid.
	except Exception:
		# Fall back to `default`, else to now.
		return default or now()
