// Copyright (c) 2026, huda and contributors
// For license information, please see license.txt
// File: mvm_settings.js
// Purpose: Settings form: the Import Old Database button.
// Created: 2026-10-07
// Last updated: 2026-10-07

// Events of the settings form.
frappe.ui.form.on("MVM Settings", {
	// System Managers can import the old MyVisitMonitor database from a .sql dump.
	refresh(frm) {
		// Only a System Manager gets the button.
		if (!frappe.user.has_role("System Manager")) return;

		// Button at the top of the form.
		frm.add_custom_button(__("Import Old Database"), () => {
			// Ask for the file and the options in a dialog.
			frappe.prompt(
				[
					// The .sql file to import.
					{
						// Name of the value.
						fieldname: "file_url",
						// File upload field.
						fieldtype: "Attach",
						// Label shown in the dialog.
						label: __("MyVisitMonitor database dump (.sql)"),
						// Must be filled in.
						reqd: 1,
					},
					// Whether the records on the site are deleted first.
					{
						// Name of the value.
						fieldname: "clear_existing",
						// Checkbox.
						fieldtype: "Check",
						// Label shown in the dialog.
						label: __("Delete existing records first"),
						// Explanation shown under the checkbox.
						description: __(
							"Removes all zones, locations, visit reasons, employees, customers and visits on this site before importing."
						),
					},
					// Whether logins are created for the old users.
					{
						// Name of the value.
						fieldname: "create_users",
						// Checkbox.
						fieldtype: "Check",
						// Label shown in the dialog.
						label: __("Create the logins of the old application"),
						// Ticked by default.
						default: 1,
						// Explanation shown under the checkbox.
						description: __("No mail is sent. Passwords are not carried over."),
					},
				],
				// Runs when the user presses Import.
				(values) => {
					// Call the server.
					frappe.call({
						// Server method that does the import.
						method: "my_visit_monitor.legacy_import.import_from_file",
						// The file and the two checkboxes.
						args: values,
						// Block the screen while it runs.
						freeze: true,
						// Text shown meanwhile.
						freeze_message: __("Importing the old database..."),
					});
				},
				// Title of the dialog.
				__("Import Old Database"),
				// Label of the button.
				__("Import")
			);
		});
	},
});
