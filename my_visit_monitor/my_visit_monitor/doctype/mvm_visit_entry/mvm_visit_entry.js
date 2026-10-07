// Copyright (c) 2026, huda and contributors
// For license information, please see license.txt

frappe.ui.form.on("MVM Visit Entry", {
	setup(frm) {
		frm.set_query("customer", () => ({ query: "my_visit_monitor.api.customer_query" }));
		frm.set_query("visit_reason", () => ({ filters: { inactive: 0 } }));
	},

	refresh(frm) {
		if (!frm.is_new() && !frm.doc.checkout_date && frm.perm[0].write) {
			frm.add_custom_button(__("Check Out"), () => check_out(frm)).addClass("btn-primary");
		}
	},

	// check in: the visit is saved with the position the browser reports
	before_save(frm) {
		if (!frm.is_new()) return;
		return get_position()
			.then((coords) => {
				frm.doc.checkin_latitude = coords.latitude;
				frm.doc.checkin_longitude = coords.longitude;
			})
			.catch((message) => {
				// the server decides whether a visit without a location is allowed
				frappe.show_alert({ message, indicator: "orange" }, 15);
			});
	},
});

function check_out(frm) {
	get_position()
		.catch((message) => {
			frappe.show_alert({ message, indicator: "orange" }, 15);
			return {};
		})
		.then((coords) =>
			frm.call("check_out", { latitude: coords.latitude, longitude: coords.longitude })
		)
		.then(() => {
			frappe.show_alert({ message: __("Out time updated successfully!"), indicator: "green" });
			frm.reload_doc();
		});
}

function get_position() {
	return new Promise((resolve, reject) => {
		if (!window.isSecureContext) {
			// browsers never share the location with a plain http:// page
			reject(
				__("Location is blocked because {0} is not an HTTPS address.", [window.location.origin])
			);
			return;
		}
		if (!navigator.geolocation) {
			reject(__("Geolocation is not supported by this browser."));
			return;
		}
		navigator.geolocation.getCurrentPosition(
			(position) => resolve(position.coords),
			(error) => reject(geolocation_error(error)),
			{ enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
		);
	});
}

function geolocation_error(error) {
	switch (error.code) {
		case error.PERMISSION_DENIED:
			return __("User denied the request for Geolocation.");
		case error.POSITION_UNAVAILABLE:
			return __("Location information is unavailable.");
		case error.TIMEOUT:
			return __("The request to get user location timed out.");
		default:
			return __("An unknown error occurred.");
	}
}
