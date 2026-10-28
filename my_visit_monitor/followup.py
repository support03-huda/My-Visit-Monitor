# File: followup.py
# Purpose: Follow-up visits. The Next Visit Date of a visit becomes a ToDo of the employee on that date; a new visit
#          to the same customer closes it. Every morning the employees get one email with the follow-up visits due
#          tomorrow (hooks.py scheduler_events), only when "Send Follow-up Reminders" is ticked in MVM Settings.
# Created: 2026-10-28
# Last updated: 2026-10-28

# Frappe framework.
import frappe
# Translation function for messages shown to the user.
from frappe import _
# Date and text helpers.
from frappe.utils import add_days, cint, escape_html, formatdate, getdate, today

# Whether an outgoing email account is set up.
from my_visit_monitor.my_visit_monitor.doctype.mvm_registration.mvm_registration import has_outgoing_email

# ToDos made here point at a visit.
REFERENCE_TYPE = "MVM Visit Entry"


# Keep the follow-up ToDo of a visit in step with its Next Visit Date (called when a visit is saved).
def sync_followup_todo(visit):
	# Open or closed ToDo made earlier for this visit; a cancelled one is left alone.
	todo_name = frappe.db.get_value(
		"ToDo", {"reference_type": REFERENCE_TYPE, "reference_name": visit.name, "status": ["!=", "Cancelled"]}
	)
	# Login of the employee who has to make the follow-up visit.
	user = frappe.db.get_value("MVM Employee", visit.employee, "user")
	# a follow-up date that has passed (old visits, imports) is no task any more
	wanted = bool(visit.next_visit_date and user and getdate(visit.next_visit_date) >= getdate(today()))

	# No follow-up wanted.
	if not wanted:
		# An open ToDo of this visit.
		if todo_name and frappe.db.get_value("ToDo", todo_name, "status") == "Open":
			# Cancel it; the date was cleared.
			frappe.db.set_value("ToDo", todo_name, "status", "Cancelled")
		# Nothing more to do.
		return

	# What the ToDo says.
	values = {
		"allocated_to": user,
		"date": visit.next_visit_date,
		"description": todo_description(visit),
	}
	# A ToDo exists already.
	if todo_name:
		# The stored ToDo.
		todo = frappe.get_doc("ToDo", todo_name)
		# a moved date is a new task again, also when the old one was closed
		if getdate(todo.date) != getdate(visit.next_visit_date):
			# Open it again.
			values["status"] = "Open"
		# New date, user and text.
		todo.update(values)
		# Save it; the employee has no right to change ToDos of others.
		todo.save(ignore_permissions=True)
		# Done.
		return
	# A new ToDo for the employee.
	frappe.get_doc(
		{
			"doctype": "ToDo",
			"status": "Open",
			"priority": "Medium",
			"reference_type": REFERENCE_TYPE,
			"reference_name": visit.name,
			"assigned_by": frappe.session.user,
			**values,
		}
	).insert(ignore_permissions=True)


# Text of the ToDo: customer, place and what the last visit was about.
def todo_description(visit):
	# City of the customer, to plan the route.
	city = frappe.db.get_value("MVM Customer", visit.customer, "city")
	# Reason of the visit, readable.
	reason = frappe.db.get_value("MVM Visit Reason", visit.visit_reason, "description") if visit.visit_reason else ""
	# One line, e.g. "Follow-up visit: SCHAEFFLER INDIA LIMITED, Talegaon. Last visit 21-10-2026 (Sales Promotion): ..."
	return _("Follow-up visit: {0}{1}. Last visit {2} ({3}): {4}").format(
		escape_html(visit.customer_name or visit.customer),
		f", {escape_html(city)}" if city else "",
		formatdate(visit.checkin_date),
		escape_html(reason or ""),
		escape_html(visit.description or ""),
	)


# A new visit to a customer is the follow-up: close the open follow-up ToDos of the employee's earlier visits there.
def close_done_followups(visit):
	# Earlier visits of the same employee to the same customer; an old visit imported later must not close
	# the follow-up of a newer one.
	earlier = frappe.get_all(
		"MVM Visit Entry",
		filters={
			"employee": visit.employee,
			"customer": visit.customer,
			"name": ["!=", visit.name],
			"checkin_date": ["<=", visit.checkin_date],
		},
		pluck="name",
	)
	# No earlier visits.
	if not earlier:
		# Nothing to close.
		return
	# Their open follow-up ToDos.
	for todo_name in frappe.get_all(
		"ToDo",
		filters={"reference_type": REFERENCE_TYPE, "reference_name": ["in", earlier], "status": "Open"},
		pluck="name",
	):
		# Done by this visit.
		frappe.db.set_value("ToDo", todo_name, "status", "Closed")


# Scheduler entry point (every morning): email every employee their follow-up visits of tomorrow.
def send_followup_reminders():
	# Switched off in MVM Settings (the default, so a test site never mails anybody).
	if not cint(frappe.db.get_single_value("MVM Settings", "followup_reminder_enabled")):
		# Nothing to do.
		return
	# No email account to send with.
	if not has_outgoing_email():
		# Leave a note in the Error Log.
		frappe.log_error(title="MVM follow-up reminders not sent", message="No default outgoing Email Account.")
		# Nothing more to do.
		return
	# Tomorrow.
	tomorrow = add_days(today(), 1)
	# Open follow-up ToDos due tomorrow.
	todos = frappe.get_all(
		"ToDo",
		filters={"reference_type": REFERENCE_TYPE, "status": "Open", "date": tomorrow},
		fields=["allocated_to", "reference_name"],
	)
	# Visits per user.
	by_user = {}
	# Every ToDo.
	for todo in todos:
		# Under its user.
		by_user.setdefault(todo.allocated_to, []).append(todo.reference_name)
	# One email per user; a failure is logged and the others still get theirs.
	for user, visits in by_user.items():
		# Build and queue the email.
		try:
			# Send it.
			send_reminder(user, visits, tomorrow)
		# Something went wrong for this user.
		except Exception:
			# Keep a record in the Error Log.
			frappe.log_error(title=f"MVM follow-up reminder to {user} failed")


# The reminder email of one user: a table of the customers to visit tomorrow.
def send_reminder(user, visit_names, date):
	# The visits that asked for the follow-up, with what the user needs to plan the day.
	visits = frappe.get_all(
		"MVM Visit Entry",
		filters={"name": ["in", visit_names]},
		fields=["name", "customer", "customer_name", "checkin_date", "visit_reason", "description"],
		order_by="customer_name asc",
	)
	# Readable visit reasons.
	reasons = dict(frappe.get_all("MVM Visit Reason", fields=["name", "description"], as_list=True))
	# Name the employee is greeted with.
	name = frappe.db.get_value("User", user, "first_name") or user
	# Style of a table cell (email programs ignore style sheets).
	cell = "border: 1px solid #d1d5db; padding: 6px 8px; text-align: left; vertical-align: top;"
	# One table row per customer.
	rows = "".join(
		f"""<tr>
			<td style="{cell}"><b>{escape_html(v.customer_name or v.customer)}</b><br>{escape_html(customer_place(v.customer))}</td>
			<td style="{cell}">{formatdate(v.checkin_date)}</td>
			<td style="{cell}">{escape_html(reasons.get(v.visit_reason, v.visit_reason or ""))}</td>
			<td style="{cell}">{escape_html(v.description or "")}</td>
		</tr>"""
		for v in visits
	)
	# Date of the visits, e.g. "Thursday, 29 Oct 2026".
	day = formatdate(date, "EEEE, d MMM yyyy")
	# Queue the email.
	frappe.sendmail(
		recipients=[user],
		subject=_("Reminder: {0} follow-up visit(s) tomorrow, {1}").format(len(visits), day),
		message=f"""<p>{_("Hello {0},").format(escape_html(name))}</p>
			<p>{_("You have planned these follow-up visits for tomorrow, {0}:").format(day)}</p>
			<table style="border-collapse: collapse; font-size: 13px;">
				<tr>
					<th style="{cell} background: #f3f4f6;">{_("Customer")}</th>
					<th style="{cell} background: #f3f4f6;">{_("Last Visit")}</th>
					<th style="{cell} background: #f3f4f6;">{_("Reason")}</th>
					<th style="{cell} background: #f3f4f6;">{_("Notes of Last Visit")}</th>
				</tr>
				{rows}
			</table>
			<p>{_("They are also in your ToDo list in My Visit Monitor.")}</p>""",
	)


# City and pincode of a customer, for the reminder.
def customer_place(customer):
	# Address parts.
	city, pincode = frappe.db.get_value("MVM Customer", customer, ["city", "pincode"]) or (None, None)
	# "Pune 411048", or empty.
	return " ".join(part for part in (city, pincode) if part)
