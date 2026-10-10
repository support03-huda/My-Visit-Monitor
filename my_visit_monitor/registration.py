# File: registration.py
# Purpose: Approval of self-registered logins: a login made through Sign Up waits for an administrator
#          before it can be used. Approval is needed only once, the first time.
# Created: 2026-10-10
# Last updated: 2026-10-10

# Frappe framework.
import frappe
# Translation function for messages shown to the user.
from frappe import _

# Roles that may approve or reject a registration ("admin").
APPROVER_ROLES = ("System Manager", "MVM Manager")


# True when the user may approve or reject registrations.
def is_approver(user=None):
	# Default to the logged-in user.
	user = user or frappe.session.user
	# Administrator, or a user holding an approver role.
	return user == "Administrator" or bool(set(APPROVER_ROLES) & set(frappe.get_roles(user)))


# Enabled users who may approve, for the notification of a new registration.
def get_approvers():
	# Users that hold one of the approver roles.
	users = frappe.get_all(
		"Has Role",
		filters={"parenttype": "User", "role": ["in", APPROVER_ROLES]},
		pluck="parent",
		distinct=True,
	)
	# Only enabled users; Administrator is a technical account and gets no notification.
	return [
		user
		for user in users
		if user != "Administrator" and frappe.db.get_value("User", user, "enabled")
	]


# Hook (User, after_insert): a login created by a visitor through Sign Up gets a registration that waits for approval.
def on_user_insert(doc, method=None):
	# Logins created by someone who is logged in (an administrator) need no approval.
	if frappe.session.user != "Guest":
		# Nothing to do.
		return
	# A registration for this login exists already.
	if frappe.db.exists("MVM Registration", {"user": doc.name}):
		# Nothing to do.
		return

	# New registration, waiting for approval.
	registration = frappe.get_doc(
		{
			"doctype": "MVM Registration",
			"user": doc.name,
			"full_name": doc.full_name or doc.first_name or doc.name,
			"email": doc.email,
			"status": "Pending",
		}
	)
	# A visitor has no permissions, so the check is skipped for this one record.
	registration.insert(ignore_permissions=True)
	# Tell the approvers.
	notify_approvers(registration)


# Put a notification (the bell at the top) for every approver.
def notify_approvers(registration):
	# A failing notification must never stop the sign up.
	try:
		# Helper of Frappe that creates the notifications in the background.
		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

		# Who gets it.
		approvers = get_approvers()
		# Nobody to tell.
		if not approvers:
			# Done.
			return
		# One notification per approver, linked to the registration.
		enqueue_create_notification(
			approvers,
			{
				"type": "Alert",
				"document_type": "MVM Registration",
				"document_name": registration.name,
				"subject": _("New login waiting for approval: {0} ({1})").format(
					registration.full_name, registration.email
				),
				"from_user": "Administrator",
			},
		)
	# Anything that went wrong.
	except Exception:
		# Keep a record in the Error Log.
		frappe.log_error(title="MVM registration notification failed")


# Hook (on_login): a self-registered login can only be used after it was approved.
def check_approval(login_manager):
	# Status of the registration of this login; None for logins made by an administrator.
	status = frappe.db.get_value("MVM Registration", {"user": login_manager.user}, "status")
	# Still waiting.
	if status == "Pending":
		# Refuse the login with the reason.
		frappe.throw(
			_("Your registration is waiting for approval. You can log in once an administrator has approved it."),
			frappe.AuthenticationError,
		)
	# Turned down.
	if status == "Rejected":
		# Refuse the login with the reason.
		frappe.throw(_("Your registration was not approved. Please contact the administrator."), frappe.AuthenticationError)
