// File: mvm_visit_entry_list.js
// Purpose: Visit list: colour of the status.
// Created: 2026-10-05
// Last updated: 2026-10-07

// Settings of the visit list.
frappe.listview_settings["MVM Visit Entry"] = {
	// Green when checked out, orange while still checked in.
	get_indicator(doc) {
		// Label, colour and the filter applied when the label is clicked.
		return doc.status === "Checked Out"
			// Checked out.
			? [__("Checked Out"), "green", "status,=,Checked Out"]
			// Still checked in.
			: [__("Checked In"), "orange", "status,=,Checked In"];
	},
};
