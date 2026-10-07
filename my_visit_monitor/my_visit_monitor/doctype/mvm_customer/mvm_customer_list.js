// File: mvm_customer_list.js
// Purpose: Customer list: the Import Magic Customers menu.
// Created: 2026-10-05
// Last updated: 2026-10-07

// Settings of the customer list.
frappe.listview_settings["MVM Customer"] = {
	// Managers get a menu item to import customers from a Magic sheet (.xlsx).
	onload(listview) {
		// Only managers get the menu item.
		if (!frappe.user.has_role(["MVM Manager", "System Manager"])) return;

		// Menu item in the list's ... menu.
		listview.page.add_menu_item(__("Import Magic Customers"), () => {
			// Ask for the file in a dialog.
			frappe.prompt(
				[
					// The sheet to import.
					{
						// Name of the value.
						fieldname: "file_url",
						// File upload field.
						fieldtype: "Attach",
						// Label shown in the dialog.
						label: __("Magic Customer Sheet (.xlsx)"),
						// Must be filled in.
						reqd: 1,
					},
					// Whether the sheet has a title row.
					{
						// Name of the value.
						fieldname: "skip_header",
						// Checkbox.
						fieldtype: "Check",
						// Label shown in the dialog.
						label: __("First row is a header"),
						// Ticked by default.
						default: 1,
					},
				],
				// Runs when the user presses Import.
				(values) => {
					// Call the server.
					frappe.call({
						// Server method that does the import.
						method: "my_visit_monitor.api.import_magic_customers",
						// The file and the checkbox.
						args: values,
						// Block the screen while it runs.
						freeze: true,
						// Text shown meanwhile.
						freeze_message: __("Importing customers..."),
						// Show the new customers in the list.
						callback: () => listview.refresh(),
					});
				},
				// Title of the dialog.
				__("Import Magic Customers"),
				// Label of the button.
				__("Import")
			);
		});
	},
};
