// Copyright (c) 2026, huda and contributors
// For license information, please see license.txt
// File: mvm_registration.js
// Purpose: Registration form: Approve and Reject buttons for administrators.
// Created: 2026-10-10
// Last updated: 2026-10-10

// Events of the registration form.
frappe.ui.form.on("MVM Registration", {
	// Show the buttons while the registration waits for a decision.
	refresh(frm) {
		// Decided already, or not an administrator.
		if (frm.doc.status !== "Pending" || !frappe.user.has_role(["System Manager", "MVM Manager"])) return;

		// Green Approve button.
		frm.add_custom_button(__("Approve"), () => approve_registration(frm)).addClass("btn-primary");
		// Reject button.
		frm.add_custom_button(__("Reject"), () => reject_registration(frm));
	},
});

// Approve: link the login to an existing employee, or leave it empty to create a new one.
function approve_registration(frm) {
	// Ask which employee this person is.
	frappe.prompt(
		[
			{
				fieldname: "employee",
				fieldtype: "Link",
				options: "MVM Employee",
				label: __("Existing Employee"),
				description: __("Leave empty to create a new employee for {0}.", [
					frappe.utils.escape_html(frm.doc.full_name || frm.doc.email),
				]),
			},
		],
		// The administrator pressed Approve.
		(values) => {
			// Approve on the server.
			frm.call("approve", { employee: values.employee || null }).then((r) => {
				// Green confirmation.
				frappe.show_alert({ message: __("Approved. The login can be used now."), indicator: "green" });
				// Show the updated registration.
				frm.reload_doc();
				// Remind to add the zones, without which the employee sees no customers.
				frappe.msgprint({
					title: __("Add zones"),
					message: __("Open employee {0} and add the zones this person works in; without zones no customers are shown.", [
						`<a href="/app/mvm-employee/${encodeURIComponent(r.message)}">${frappe.utils.escape_html(r.message)}</a>`,
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
