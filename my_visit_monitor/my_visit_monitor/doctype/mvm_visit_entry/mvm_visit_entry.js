// Copyright (c) 2026, huda and contributors
// For license information, please see license.txt
// File: mvm_visit_entry.js
// Purpose: Visit entry form: customer filter, check-in position, Check Out button and location check colours.
// Created: 2026-10-05
// Last updated: 2026-10-07

// Events of the visit form.
frappe.ui.form.on("MVM Visit Entry", {
	// Only customers the employee may visit, and only active reasons.
	setup(frm) {
		// The customer list comes from the server (zones of the employee).
		frm.set_query("customer", () => ({ query: "my_visit_monitor.api.customer_query" }));
		// Inactive reasons are not offered.
		frm.set_query("visit_reason", () => ({ filters: { inactive: 0 } }));
	},

	// Colour the location checks and show Check Out on a visit that is still checked in.
	refresh(frm) {
		// Check-in: green inside the radius, red outside.
		color_location_check(frm, "location_remark", frm.doc.checkin_location_status);
		// Check-out: green inside the radius, red outside.
		color_location_check(frm, "checkout_location_remark", frm.doc.checkout_location_status);
		// Saved, not checked out yet, and the user may change it.
		if (!frm.is_new() && !frm.doc.checkout_date && frm.perm[0].write) {
			// Blue Check Out button.
			frm.add_custom_button(__("Check Out"), () => check_out(frm)).addClass("btn-primary");
		}
	},

	// check in: the visit is saved with the position the browser reports
	before_save(frm) {
		// Only a new visit is checked in.
		if (!frm.is_new()) return;
		// Wait for the position before the visit is saved.
		return get_position()
			// The browser gave a position.
			.then((coords) => {
				// Check-in latitude.
				frm.doc.checkin_latitude = coords.latitude;
				// Check-in longitude.
				frm.doc.checkin_longitude = coords.longitude;
			})
			// The browser gave no position.
			.catch((message) => {
				// the server decides whether a visit without a location is allowed
				// Tell the user why, for 15 seconds.
				frappe.show_alert({ message, indicator: "orange" }, 15);
			});
	},
});

// Text colour per status of a location check.
const LOCATION_COLORS = { Inside: "#2f9e44", Outside: "#e03131" };

// Show the sentence of a location check in green (inside) or red (outside).
function color_location_check(frm, fieldname, status) {
	// The read-only text of the field.
	const $value = frm.get_field(fieldname).$wrapper.find(".control-value");
	// Green or red; the normal colour when there is no status.
	$value.css("color", LOCATION_COLORS[status] || "");
	// Bold when coloured.
	$value.css("font-weight", LOCATION_COLORS[status] ? 600 : "");
}

// Check out with the current position; the server decides whether a position is required.
function check_out(frm) {
	// Ask the browser for the position.
	get_position()
		// The browser gave no position.
		.catch((message) => {
			// Tell the user why, for 15 seconds.
			frappe.show_alert({ message, indicator: "orange" }, 15);
			// Carry on without a position.
			return {};
		})
		// With or without a position.
		.then((coords) =>
			// Check out on the server.
			frm.call("check_out", { latitude: coords.latitude, longitude: coords.longitude })
		)
		// The check-out is saved.
		.then(() => {
			// Green confirmation.
			frappe.show_alert({ message: __("Out time updated successfully!"), indicator: "green" });
			// Show the saved visit.
			frm.reload_doc();
		});
}

// Ask the browser for the current position.
function get_position() {
	// Resolves with the position, rejects with a message.
	return new Promise((resolve, reject) => {
		// The page is not served over HTTPS.
		if (!window.isSecureContext) {
			// browsers never share the location with a plain http:// page
			// Reject with the reason.
			reject(
				__("Location is blocked because {0} is not an HTTPS address.", [window.location.origin])
			);
			// Stop here.
			return;
		}
		// The browser has no geolocation.
		if (!navigator.geolocation) {
			// Reject with the reason.
			reject(__("Geolocation is not supported by this browser."));
			// Stop here.
			return;
		}
		// Ask the browser; this may show its permission prompt.
		navigator.geolocation.getCurrentPosition(
			// Success: latitude and longitude.
			(position) => resolve(position.coords),
			// Failure: a readable message.
			(error) => reject(geolocation_error(error)),
			// Use GPS when available, wait at most 10 seconds, never an old position.
			{ enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
		);
	});
}

// Readable message for a geolocation error.
function geolocation_error(error) {
	// The browser reports a code.
	switch (error.code) {
		// The user refused the permission.
		case error.PERMISSION_DENIED:
			// Message for a refused permission.
			return __("User denied the request for Geolocation.");
		// The device could not find its position.
		case error.POSITION_UNAVAILABLE:
			// Message for an unknown position.
			return __("Location information is unavailable.");
		// It took too long.
		case error.TIMEOUT:
			// Message for a timeout.
			return __("The request to get user location timed out.");
		// Anything else.
		default:
			// Message for an unknown error.
			return __("An unknown error occurred.");
	}
}
