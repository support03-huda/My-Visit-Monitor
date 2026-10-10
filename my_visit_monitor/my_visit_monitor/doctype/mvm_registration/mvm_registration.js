// Copyright (c) 2026, huda and contributors
// For license information, please see license.txt
// File: mvm_registration.js
// Purpose: Registration form: Approve (employee, manager, role) and Reject buttons for admins and managers.
// Created: 2026-10-10
// Last updated: 2026-10-10

// Events of the registration form.
frappe.ui.form.on("MVM Registration", {
	// Show the buttons while the registration waits for a decision.
	refresh(frm) {
		// Decided already, or the user may not decide (the server says who may: admins and team managers).
		if (frm.doc.status !== "Pending" || !(frm.doc.__onload || {}).can_decide) return;

		// Green Approve button.
		frm.add_custom_button(__("Approve"), () => approve_registration(frm)).addClass("btn-primary");
		// Reject button.
		frm.add_custom_button(__("Reject"), () => reject_registration(frm));
	},
});

// Approve: link the login to the existing employee (found by email) or a new one, set the manager and the role.
function approve_registration(frm) {
	// What the server worked out for this registration.
	const onload = frm.doc.__onload || {};
	// Ask which employee this person is, who their manager is and what they become.
	frappe.prompt(
		[
			{
				fieldname: "employee",
				fieldtype: "Link",
				options: "MVM Employee",
				label: __("Existing Employee"),
				// The employee with the same email, when there is one.
				default: onload.existing_employee,
				description: onload.existing_employee
					? __("Found by email. Change it only if this is someone else.")
					: __("No employee with this email. Leave empty to create a new employee for {0}.", [
							frappe.utils.escape_html(frm.doc.full_name || frm.doc.email),
					  ]),
			},
			{
				fieldname: "role",
				fieldtype: "Select",
				label: __("Role"),
				// Managers may only approve employees.
				options: onload.is_admin ? ["Employee", "Manager", "Admin"].join("\n") : "Employee",
				default: "Employee",
				reqd: 1,
				description: __("Employee: own work only. Manager: own team. Admin: everything."),
			},
			{
				fieldname: "reporting_to",
				fieldtype: "Link",
				options: "MVM Employee",
				label: __("Reports To (Manager)"),
				// A team manager's own employee by default.
				default: (frm.doc.__onload || {}).default_manager,
			},
		],
		// The approver pressed Approve.
		(values) => {
			// Approve on the server.
			frm.call("approve", {
				employee: values.employee || null,
				reporting_to: values.reporting_to || null,
				role: values.role || "Employee",
			}).then((r) => {
				// Employee of the login and whether the set-password email went out.
				const { employee, mail_sent } = r.message;
				// Green confirmation, or how to give the password when no email could be sent.
				frappe.show_alert(
					{
						message: mail_sent
							? __("Approved. An email to set the password was sent to {0}.", [frappe.utils.escape_html(frm.doc.email)])
							: __("Approved, but no email could be sent: the site has no outgoing email account. Set the password on the user (User > Password > Set Password) and tell the person."),
						indicator: mail_sent ? "green" : "orange",
					},
					15
				);
				// Show the updated registration.
				frm.reload_doc();
				// An existing employee keeps the zones it has: nothing to remind.
				if (values.employee) return;
				// Remind to add the zones, without which the employee sees no customers.
				frappe.msgprint({
					title: __("Add zones"),
					message: __("New employee {0} has no zones yet. The employee can add them on their own record, or open it and add them now; without zones no customers are shown.", [
						`<a href="/app/mvm-employee/${encodeURIComponent(employee)}">${frappe.utils.escape_html(employee)}</a>`,
					]),
					indicator: "blue",
				});
			});
		},
		// Title of the dialog.
		__("Approve Registration"),
		// Label of its button.
		__("Approve")
	);
}

// Reject: the login stays switched off.
function reject_registration(frm) {
	// Ask for an optional reason.
	frappe.prompt(
		[{ fieldname: "remarks", fieldtype: "Small Text", label: __("Reason (optional)") }],
		// The administrator pressed Reject.
		(values) => {
			// Reject on the server.
			frm.call("reject", { remarks: values.remarks || null }).then(() => {
				// Confirmation.
				frappe.show_alert({ message: __("Registration rejected."), indicator: "orange" });
				// Show the updated registration.
				frm.reload_doc();
			});
		},
		// Title of the dialog.
		__("Reject Registration"),
		// Label of its button.
		__("Reject")
	);
}
