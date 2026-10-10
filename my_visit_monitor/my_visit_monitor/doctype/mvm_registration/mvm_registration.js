// Copyright (c) 2026, huda and contributors
// For license information, please see license.txt
// File: mvm_registration.js
// Purpose: Registration form: Approve and Reject buttons for admins and team managers.
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

// Approve: link the login to an existing employee or create a new one, and set the zones and the manager.
function approve_registration(frm) {
	// Ask which employee this person is, where they work and who their manager is.
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
			{
				fieldname: "zones",
				// A plain list of zone names; a "Table MultiSelect" fails in a dialog because the child table
				// is not loaded there, which made the Approve button do nothing.
				fieldtype: "MultiSelectList",
				label: __("Zones"),
				description: __("Zones this person works in; their customers are shown to them."),
				// Zones matching what is typed, from the zone master.
				get_data: (text) => frappe.db.get_link_options("MVM Zone", text),
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
			// Chosen zone names.
			const zones = (values.zones || []).filter(Boolean);
			// Approve on the server.
			frm.call("approve", {
				employee: values.employee || null,
				zones,
				reporting_to: values.reporting_to || null,
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
				// Zones were chosen in the dialog: nothing to remind.
				if (zones.length) return;
				// Remind to add the zones, without which the employee sees no customers.
				frappe.msgprint({
					title: __("Add zones"),
					message: __("Open employee {0} and add the zones this person works in; without zones no customers are shown.", [
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
