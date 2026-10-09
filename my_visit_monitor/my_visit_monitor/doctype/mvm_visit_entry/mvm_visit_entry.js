// Copyright (c) 2026, huda and contributors
// For license information, please see license.txt
// File: mvm_visit_entry.js
// Purpose: Visit entry form: customer filter, check-in position, Check Out button, location check colours
//          the map with the check-in, check-out and customer marks, the accuracy of the captured position
//          and the manager button that makes a check-in position the customer location.
// Created: 2026-10-05
// Last updated: 2026-10-09

// Events of the visit form.
frappe.ui.form.on("MVM Visit Entry", {
	// Only customers the employee may visit, and only active reasons.
	setup(frm) {
		// The customer list comes from the server (zones of the employee).
		frm.set_query("customer", () => ({ query: "my_visit_monitor.api.customer_query" }));
		// Inactive reasons are not offered.
		frm.set_query("visit_reason", () => ({ filters: { inactive: 0 } }));
	},

	// Draw the map, colour the location checks and show Check Out on a visit that is still checked in.
	refresh(frm) {
		// Map with the check-in, check-out and customer marks.
		render_map(frm);
		// Check-in: green inside the radius, red outside.
		color_location_check(frm, "location_remark", frm.doc.checkin_location_status);
		// Check-out: green inside the radius, red outside.
		color_location_check(frm, "checkout_location_remark", frm.doc.checkout_location_status);
		// Saved, not checked out yet, and the user may change it.
		if (!frm.is_new() && !frm.doc.checkout_date && frm.perm[0].write) {
			// Blue Check Out button.
			frm.add_custom_button(__("Check Out"), () => check_out(frm)).addClass("btn-primary");
		}
		// A manager can make the check-in position of this visit the location of the customer.
		if (
			!frm.is_new() &&
			(frm.doc.checkin_latitude || frm.doc.checkin_longitude) &&
			frappe.user.has_role(["MVM Manager", "System Manager"])
		) {
			// Button in the bar above the form.
			frm.add_custom_button(__("Set as Customer Location"), () => set_customer_location(frm));
		}
	},

	// check in: the visit is saved with the position the browser reports
	before_save(frm) {
		// Only a new visit is checked in.
		if (!frm.is_new()) return;
		// Reading the position can take a few seconds; show that and block double clicks.
		frappe.dom.freeze(__("Getting your location..."));
		// Wait for the position before the visit is saved.
		return get_position()
			// The browser gave a position.
			.then((coords) => {
				// Check-in latitude.
				frm.doc.checkin_latitude = coords.latitude;
				// Check-in longitude.
				frm.doc.checkin_longitude = coords.longitude;
				// How exact the position is, in metres.
				frm.doc.checkin_accuracy = coords.accuracy || 0;
				// Tell the user when the position is too rough to trust.
				warn_poor_accuracy(coords);
			})
			// The browser gave no position.
			.catch((message) => {
				// the server decides whether a visit without a location is allowed
				// Tell the user why, for 15 seconds.
				frappe.show_alert({ message, indicator: "orange" }, 15);
			})
			// With or without a position.
			.then(() => {
				// Let the user work again.
				frappe.dom.unfreeze();
			});
	},
});

// Colours of the marks on the map.
const MAP_CHECKIN_COLOR = "#2f9e44";
const MAP_CHECKOUT_COLOR = "#e03131";
const MAP_CUSTOMER_COLOR = "#1c7ed6";

// Map of the visit: green mark where the employee checked in, red mark where they checked out,
// blue mark for the customer.
function render_map(frm) {
	// The HTML field the map is drawn into.
	const $wrapper = frm.get_field("location_map").$wrapper;
	// A map drawn earlier for this form.
	if (frm.mvm_map) {
		// Remove it, so the form does not keep two maps.
		frm.mvm_map.remove();
		// Forget it.
		frm.mvm_map = null;
	}

	// The three positions; check-out is drawn smaller and on top, so check-in stays visible
	// when both are at the same spot.
	const marks = [
		{
			label: __("Check In"),
			// Name of the colour, written in the legend under the map.
			color_name: __("Green"),
			color: MAP_CHECKIN_COLOR,
			radius: 11,
			lat: frm.doc.checkin_latitude,
			lng: frm.doc.checkin_longitude,
		},
		{
			label: __("Check Out"),
			color_name: __("Red"),
			color: MAP_CHECKOUT_COLOR,
			radius: 7,
			lat: frm.doc.checkout_latitude,
			lng: frm.doc.checkout_longitude,
		},
		{
			label: __("Customer"),
			color_name: __("Blue"),
			color: MAP_CUSTOMER_COLOR,
			radius: 5,
			lat: frm.doc.customer_latitude,
			lng: frm.doc.customer_longitude,
		},
	];
	// Only positions that were captured are drawn; 0, 0 means there is none.
	const points = marks.filter((point) => point.lat || point.lng);

	// A new visit, or a visit without any position, has nothing to show.
	if (frm.is_new() || !points.length) {
		// Say so instead of an empty map.
		$wrapper.html(`<div class="text-muted">${__("No location was captured for this visit.")}</div>`);
		// Nothing to draw.
		return;
	}

	// Line under the map for all three marks: a coloured dot, the colour name, what it marks and the
	// coordinates, e.g. "Green - Check In: 18.557875, 73.907321"; "not captured" when there is no position.
	const legend = marks
		.map(
			(point) =>
				`<span style="margin-right: 16px; white-space: nowrap;">
					<span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: ${point.color};"></span>
					${point.color_name} - ${point.label}: ${point.lat || point.lng ? `${flt(point.lat, 6)}, ${flt(point.lng, 6)}` : __("not captured")}
				</span>`
		)
		.join("");
	// The box for the map and the legend under it.
	$wrapper.html(
		`<div class="mvm-visit-map" style="height: 320px; border-radius: var(--border-radius); z-index: 0;"></div>
		<div class="small text-muted" style="margin-top: 8px;">${legend}</div>`
	);

	// Street map tiles Frappe uses everywhere (OpenStreetMap).
	const tile = frappe.utils.map_defaults.tiles.default_tile;
	// Create the map in the box and remember it on the form.
	const map = (frm.mvm_map = L.map($wrapper.find(".mvm-visit-map").get(0)));
	// Show the street map.
	L.tileLayer(tile.url, tile.options).addTo(map);

	// One round mark per position.
	points.forEach((point) => {
		// A filled circle with a white edge; hovering shows its name.
		L.circleMarker([point.lat, point.lng], {
			radius: point.radius,
			color: "#ffffff",
			weight: 2,
			fillColor: point.color,
			fillOpacity: 1,
		})
			.addTo(map)
			.bindTooltip(point.label);
	});

	// The area that contains all marks.
	const bounds = L.latLngBounds(points.map((point) => [point.lat, point.lng]));
	// Zoom to that area, but not closer than street level.
	map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
	// The section may still be laying out when the map is created; measure it again shortly after.
	setTimeout(() => frm.mvm_map === map && map.invalidateSize(), 300);
}

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
	// Reading the position can take a few seconds; show that and block double clicks.
	frappe.dom.freeze(__("Getting your location..."));
	// Ask the browser for the position.
	get_position()
		// The browser gave a position.
		.then((coords) => {
			// Tell the user when the position is too rough to trust.
			warn_poor_accuracy(coords);
			// Pass the position on.
			return coords;
		})
		// The browser gave no position.
		.catch((message) => {
			// Tell the user why, for 15 seconds.
			frappe.show_alert({ message, indicator: "orange" }, 15);
			// Carry on without a position.
			return {};
		})
		// With or without a position.
		.then((coords) => {
			// Let the user work again.
			frappe.dom.unfreeze();
			// Check out on the server, with the position and how exact it is.
			return frm.call("check_out", {
				latitude: coords.latitude,
				longitude: coords.longitude,
				accuracy: coords.accuracy,
			});
		})
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
		// The most exact position seen so far.
		let best = null;
		// The last error the browser reported.
		let failure = null;
		// Stop listening and hand over the best position, or the reason there is none.
		const finish = () => {
			// Stop the GPS.
			navigator.geolocation.clearWatch(watch);
			// Stop the timer.
			clearTimeout(timer);
			// A position was found.
			if (best) resolve(best);
			// No position at all.
			else reject(failure ? geolocation_error(failure) : __("The request to get user location timed out."));
		};
		// Keep reading: the first position is often rough and gets better within seconds.
		// This may show the permission prompt of the browser.
		const watch = navigator.geolocation.watchPosition(
			// A new position came in.
			(position) => {
				// Keep it when it is the first one or more exact than the best so far.
				if (!best || position.coords.accuracy < best.accuracy) best = position.coords;
				// Exact enough: no need to wait any longer.
				if (best.accuracy <= GOOD_ACCURACY) finish();
			},
			// The browser reported an error.
			(error) => {
				// Remember it for the message.
				failure = error;
				// A refused permission will not get better by waiting.
				if (error.code === error.PERMISSION_DENIED) finish();
			},
			// Use GPS when available and never an old position.
			{ enableHighAccuracy: true, maximumAge: 0 }
		);
		// Take the best position seen when the waiting time is over.
		const timer = setTimeout(finish, POSITION_WAIT);
	});
}

// A position this exact (in metres) is taken at once.
const GOOD_ACCURACY = 20;
// Longest time to wait for a better position, in milliseconds.
const POSITION_WAIT = 10000;
// A position less exact than this (in metres) is saved with a warning.
const POOR_ACCURACY = 100;

// Tell the user when the phone only knows roughly where it is.
function warn_poor_accuracy(coords) {
	// Exact enough, or the browser did not say.
	if (!coords.accuracy || coords.accuracy <= POOR_ACCURACY) return;
	// Orange message for 15 seconds, with what helps.
	frappe.show_alert(
		{
			message: __(
				"Your location is only accurate to about {0} m. Switch on GPS / Location and stand outdoors for an exact check.",
				[Math.round(coords.accuracy)]
			),
			indicator: "orange",
		},
		15
	);
}

// Manager: make the check-in position of this visit the location of its customer.
function set_customer_location(frm) {
	// How exact the check-in position was, for the question.
	const accuracy = frm.doc.checkin_accuracy
		? __("The position is accurate to about {0} m.", [Math.round(frm.doc.checkin_accuracy)])
		: __("The accuracy of this position was not recorded.");
	// Ask first: this changes the customer for all later visits.
	frappe.confirm(
		__("Use the check-in position of this visit ({0}, {1}) as the location of customer {2}? {3}", [
			flt(frm.doc.checkin_latitude, 6),
			flt(frm.doc.checkin_longitude, 6),
			frappe.utils.escape_html(frm.doc.customer_name || frm.doc.customer),
			accuracy,
		]),
		// The manager said yes.
		() => {
			// Store the position on the customer.
			frm.call("use_checkin_as_customer_location").then(() => {
				// Green confirmation.
				frappe.show_alert({ message: __("Customer location updated."), indicator: "green" });
			});
		}
	);
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
