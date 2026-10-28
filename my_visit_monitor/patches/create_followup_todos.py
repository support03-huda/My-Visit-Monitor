# File: create_followup_todos.py
# Purpose: One-time patch: ToDos for the follow-up visits planned before follow-up ToDos existed. Per employee and
#          customer only the latest visit counts, and only when its Next Visit Date is today or later.
# Created: 2026-10-28
# Last updated: 2026-10-28

# Frappe framework.
import frappe
# Today's date.
from frappe.utils import today

# Makes or updates the ToDo of one visit.
from my_visit_monitor.followup import sync_followup_todo


# Frappe runs this once per site, during migrate.
def execute():
	# Latest visit per employee and customer, with a follow-up date still to come.
	names = frappe.db.sql_list(
		"""
		select v.name from `tabMVM Visit Entry` v
		where v.next_visit_date >= %(today)s
			and not exists (
				select 1 from `tabMVM Visit Entry` later
				where later.employee = v.employee and later.customer = v.customer
					and (later.checkin_date > v.checkin_date
						or (later.checkin_date = v.checkin_date and later.name > v.name)))
		""",
		{"today": today()},
	)
	# One ToDo per visit.
	for name in names:
		# Same code as when a visit is saved.
		sync_followup_todo(frappe.get_doc("MVM Visit Entry", name))
