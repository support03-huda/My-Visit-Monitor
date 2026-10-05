frappe.listview_settings["MVM Customer"] = {
	onload(listview) {
		if (!frappe.user.has_role(["MVM Manager", "System Manager"])) return;

		listview.page.add_menu_item(__("Import Magic Customers"), () => {
			frappe.prompt(
				[
					{
						fieldname: "file_url",
						fieldtype: "Attach",
						label: __("Magic Customer Sheet (.xlsx)"),
						reqd: 1,
					},
					{
						fieldname: "skip_header",
						fieldtype: "Check",
						label: __("First row is a header"),
						default: 1,
					},
				],
				(values) => {
					frappe.call({
						method: "my_visit_monitor.api.import_magic_customers",
						args: values,
						freeze: true,
						freeze_message: __("Importing customers..."),
						callback: () => listview.refresh(),
					});
				},
				__("Import Magic Customers"),
				__("Import")
			);
		});
	},
};
