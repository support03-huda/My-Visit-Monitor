// File: mvm_visit_entry_list.js
// Purpose: Visit list: colour of the status, and a red Check Out button on visits that are still checked in.
// Created: 2026-10-05
// Last updated: 2026-10-10

// Settings of the visit list.
frappe.listview_settings["MVM Visit Entry"] = {
	// Fields the list needs for the button, also when they are not shown as columns.
	add_fields: ["status", "employee"],

	// Green when checked out, orange while still checked in.
	get_indicator(doc) {
		// Label, colour and the filter applied when the label is clicked.
		return doc.status === "Checked Out"
			// Checked out.
			? [__("Checked Out"), "green", "status,=,Checked Out"]
			// Still checked in.
			: [__("Checked In"), "orange", "status,=,Checked In"];
	},

	// Runs after the rows are drawn.
	refresh(listview) {
		// Frappe draws the row button grey; make every Check Out button red.
		listview.$result.find(".btn-action").removeClass("btn-default").addClass("btn-danger");
	},

	// Button at the end of each row.
	button: {
		// Only on visits that are still checked in.
		show(doc) {
			// Checked in, not out yet.
			return doc.status === "Checked In";
		},
		// Text of the button.
		get_label() {
			// Same words as on the form.
			return __("Check Out");
		},
		// Hover text.
		get_description(doc) {
			// Which visit is checked out.
			return __("Check out visit {0}", [doc.name]);
		},
		// The button was clicked.
		action(doc) {
			// Read the position and save the check-out (shared helper in public/js/mvm_position.js).
			my_visit_monitor.position.check_out(doc.name).then(() => {
				// Show the new status in the list.
				cur_list && cur_list.refresh();
			});
		},
	},
};
