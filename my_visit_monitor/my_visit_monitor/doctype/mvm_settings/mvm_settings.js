// Copyright (c) 2026, huda and contributors
// For license information, please see license.txt

frappe.ui.form.on("MVM Settings", {
	refresh(frm) {
		if (!frappe.user.has_role("System Manager")) return;

		frm.add_custom_button(__("Import Old Database"), () => {
			frappe.prompt(
				[
					{
						fieldname: "file_url",
						fieldtype: "Attach",
						label: __("MyVisitMonitor database dump (.sql)"),
						reqd: 1,
					},
					{
						fieldname: "clear_existing",
						fieldtype: "Check",
						label: __("Delete existing records first"),
						description: __(
							"Removes all zones, locations, visit reasons, employees, customers and visits on this site before importing."
						),
					},
					{
						fieldname: "create_users",
						fieldtype: "Check",
						label: __("Create the logins of the old application"),
						default: 1,
						description: __("No mail is sent. Passwords are not carried over."),
					},
				],
				(values) => {
					frappe.call({
						method: "my_visit_monitor.legacy_import.import_from_file",
						args: values,
						freeze: true,
						freeze_message: __("Importing the old database..."),
					});
				},
				__("Import Old Database"),
				__("Import")
			);
		});
	},
});
