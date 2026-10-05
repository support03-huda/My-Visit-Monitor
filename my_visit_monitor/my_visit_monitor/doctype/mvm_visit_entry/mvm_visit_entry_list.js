frappe.listview_settings["MVM Visit Entry"] = {
	get_indicator(doc) {
		return doc.status === "Checked Out"
			? [__("Checked Out"), "green", "status,=,Checked Out"]
			: [__("Checked In"), "orange", "status,=,Checked In"];
	},
};
