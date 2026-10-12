// Copyright (c) 2026, huda and contributors
// For license information, please see license.txt
// File: mvm_registration.js
// Purpose: Registration form: Approve (employee, manager, role) and Reject buttons for admins and managers.
//          For an existing employee the dialog is filled in from the employee record.
// Created: 2026-10-10
// Last updated: 2026-10-12

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
	// The employee record found by email: its manager, role and zones are the defaults of the dialog.
	const existing = onload.existing_details || {};
	// The dialog, once it is open (the employee field needs it when another employee is chosen).
	let dialog = null;
	// Ask which employee this person is, who their manager is and what they become.
	dialog = frappe.prompt(
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
				// Another employee was chosen: fill the dialog in from that record.
				onchange() {
					// While the dialog is being built there is nothing to update yet.
					if (!dialog) return;
					// The employee chosen now.
					const employee = dialog.get_value("employee") || null;
					// The same one as shown already (the field also fires when it is only left).
					if (employee === dialog.shown_employee) return;
					// Remember it.
					dialog.shown_employee = employee;
					// Manager, role and zones of the chosen employee.
					frm.call("employee_details", { employee }).then((r) => {
						// Put them into the dialog.
						fill_from_employee(dialog, r.message, onload);
					});
				},
			},
			{
				// What the employee record says, so the approver sees it before approving.
				fieldname: "details",
				fieldtype: "HTML",
				options: employee_summary(existing),
			},
			{
				fieldname: "role",
				fieldtype: "Select",
				label: __("Role"),
				// Managers may only approve employees.
				options: onload.is_admin ? ["Employee", "Manager", "Admin"].join("\n") : "Employee",
				// A team manager in the employee record becomes Manager, everybody else Employee.
				default: existing.role || "Employee",
				reqd: 1,
				description: __("Employee: own work only. Manager: own team. Admin: everything."),
			},
			{
				fieldname: "reporting_to",
				fieldtype: "Link",
				options: "MVM Employee",
				label: __("Reports To (Manager)"),
				// The manager in the employee record; for a new employee a team manager's own employee.
				default: existing.reporting_to || onload.default_manager,
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
	// The employee the dialog shows at the start.
	dialog.shown_employee = onload.existing_employee || null;
}

// Put the manager, role and summary of an employee record into the approval dialog.
function fill_from_employee(dialog, details, onload) {
	// Nothing chosen means a new employee: back to the defaults.
	details = details || {};
	// The manager of the record, else a team manager's own employee.
	dialog.set_value("reporting_to", details.reporting_to || onload.default_manager || "");
	// Manager for someone with a team, else Employee.
	dialog.set_value("role", details.role || "Employee");
	// The summary under the employee field.
	dialog.fields_dict.details.$wrapper.html(employee_summary(details));
}

// Short summary of an employee record: name, manager, location, mobile and zones.
function employee_summary(details) {
	// No existing employee: nothing to show.
	if (!details || !details.employee) return "";
	// Text safe to put into HTML.
	const esc = frappe.utils.escape_html;
	// Label and value pairs; empty values are left out.
	const lines = [
		[__("Employee"), `${details.employee_name || ""} (${details.employee})`],
		[__("Reports To"), details.reporting_to ? `${details.reporting_to_name || ""} (${details.reporting_to})` : ""],
		[__("Location"), details.location],
		[__("Mobile"), details.mobile],
		[__("Zones"), (details.zones || []).join(", ")],
	].filter(([, value]) => value);
	// A small grey block with one line per value.
	return `<div class="text-muted small" style="margin-bottom: var(--margin-md)">
		<div>${__("From the employee record:")}</div>
		${lines.map(([label, value]) => `<div>${esc(label)}: <b>${esc(String(value))}</b></div>`).join("")}
	</div>`;
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
