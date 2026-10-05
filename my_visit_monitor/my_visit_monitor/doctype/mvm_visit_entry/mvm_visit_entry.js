// Copyright (c) 2026, huda and contributors
// For license information, please see license.txt

frappe.ui.form.on("MVM Visit Entry", {
	setup(frm) {
		frm.set_query("customer", () => ({ query: "my_visit_monitor.api.customer_query" }));
		frm.set_query("visit_reason", () => ({ filters: { inactive: 0 } }));
	},

	refresh(frm) {
		render_map(frm);
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

const CHECKIN_COLOR = "#2f9e44";
const CHECKOUT_COLOR = "#e03131";

// green dot where the employee checked in, red dot where they checked out
function render_map(frm) {
	const $wrapper = frm.get_field("location_map").$wrapper;
	if (frm.mvm_map) {
		frm.mvm_map.remove();
		frm.mvm_map = null;
	}

	// check-out is drawn smaller and on top, so both stay visible when they are at the same spot
	const points = [
		{
			label: __("Check In"),
			color: CHECKIN_COLOR,
			radius: 11,
			lat: frm.doc.checkin_latitude,
			lng: frm.doc.checkin_longitude,
		},
		{
			label: __("Check Out"),
			color: CHECKOUT_COLOR,
			radius: 6,
			lat: frm.doc.checkout_latitude,
			lng: frm.doc.checkout_longitude,
		},
	].filter((point) => point.lat || point.lng);

	if (frm.is_new() || !points.length) {
		$wrapper.html(`<div class="text-muted">${__("No location was captured for this visit.")}</div>`);
		return;
	}

	const legend = points
		.map(
			(point) =>
				`<span style="margin-right: 16px; white-space: nowrap;">
					<span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: ${point.color};"></span>
					${point.label}: ${flt(point.lat, 6)}, ${flt(point.lng, 6)}
				</span>`
		)
		.join("");
	$wrapper.html(
		`<div class="mvm-visit-map" style="height: 320px; border-radius: var(--border-radius); z-index: 0;"></div>
		<div class="small text-muted" style="margin-top: 8px;">${legend}</div>`
	);

	const tile = frappe.utils.map_defaults.tiles.default_tile;
	const map = (frm.mvm_map = L.map($wrapper.find(".mvm-visit-map").get(0)));
	L.tileLayer(tile.url, tile.options).addTo(map);

	points.forEach((point) => {
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

	const bounds = L.latLngBounds(points.map((point) => [point.lat, point.lng]));
	map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
	// the section may still be laying out when the map is created
	setTimeout(() => frm.mvm_map === map && map.invalidateSize(), 300);
}

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
