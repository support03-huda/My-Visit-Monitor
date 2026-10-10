// File: mvm_registration_list.js
// Purpose: Registration list: colour of the status.
// Created: 2026-10-10
// Last updated: 2026-10-10

// Settings of the registration list.
frappe.listview_settings["MVM Registration"] = {
	// Orange while waiting, green when approved, red when rejected.
	get_indicator(doc) {
		// Colour per status.
		const colors = { Pending: "orange", Approved: "green", Rejected: "red" };
		// Label, colour and the filter applied when the label is clicked.
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
