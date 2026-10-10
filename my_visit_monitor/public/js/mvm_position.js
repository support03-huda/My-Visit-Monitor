// File: mvm_position.js
// Purpose: Reading the phone's position for check-in and check-out, shared by the visit form and the visit list
//          (added to both through doctype_js / doctype_list_js in hooks.py).
// Created: 2026-10-10
// Last updated: 2026-10-10

// Make sure the namespace exists; the file may be loaded more than once.
frappe.provide("my_visit_monitor");

// Position helpers: my_visit_monitor.position.get(), .warn_poor_accuracy(), .error_message().
my_visit_monitor.position = {
	// A position this exact (in metres) is taken at once.
	GOOD_ACCURACY: 20,
	// Longest time to wait for a better position, in milliseconds.
	WAIT: 10000,
	// A position less exact than this (in metres) is saved with a warning.
	POOR_ACCURACY: 100,

	// Ask the browser for the current position; resolves with the most exact one seen, rejects with a message.
	get() {
		// The settings above.
		const settings = this;
		// Promise for the caller.
		return new Promise((resolve, reject) => {
			// The page is not served over HTTPS.
			if (!window.isSecureContext) {
				// browsers never share the location with a plain http:// page
				reject(__("Location is blocked because {0} is not an HTTPS address.", [window.location.origin]));
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
			// Id of the running GPS watch.
			let watch = null;
			// Id of the waiting timer.
			let timer = null;
			// Stop listening and hand over the best position, or the reason there is none.
			const finish = () => {
				// Stop the GPS.
				navigator.geolocation.clearWatch(watch);
				// Stop the timer.
				clearTimeout(timer);
				// A position was found.
				if (best) resolve(best);
				// No position at all.
				else reject(failure ? settings.error_message(failure) : __("The request to get user location timed out."));
			};
			// Keep reading: the first position is often rough and gets better within seconds.
			// This may show the permission prompt of the browser.
			watch = navigator.geolocation.watchPosition(
				// A new position came in.
				(position) => {
					// Keep it when it is the first one or more exact than the best so far.
					if (!best || position.coords.accuracy < best.accuracy) best = position.coords;
					// Exact enough: no need to wait any longer.
					if (best.accuracy <= settings.GOOD_ACCURACY) finish();
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
			timer = setTimeout(finish, settings.WAIT);
		});
	},

	// Tell the user when the phone only knows roughly where it is.
	warn_poor_accuracy(coords) {
		// Exact enough, or the browser did not say.
		if (!coords.accuracy || coords.accuracy <= this.POOR_ACCURACY) return;
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
	},

	// Readable message for a geolocation error.
	error_message(error) {
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
	},

	// Check out a visit: read the position, then save the check-out on the server. Resolves when saved.
	check_out(visit) {
		// Reading the position can take a few seconds; show that and block double clicks.
		frappe.dom.freeze(__("Getting your location..."));
		// Ask the browser for the position.
		return this.get()
			// The browser gave a position.
			.then((coords) => {
				// Tell the user when the position is too rough to trust.
				this.warn_poor_accuracy(coords);
				// Pass the position on.
				return coords;
			})
			// The browser gave no position.
			.catch((message) => {
				// Tell the user why, for 15 seconds.
				frappe.show_alert({ message, indicator: "orange" }, 15);
				// Carry on without a position; the server decides whether one is required.
				return {};
			})
			// With or without a position.
			.then((coords) => {
				// Let the user work again.
				frappe.dom.unfreeze();
				// Check out on the server, with the position and how exact it is.
				return frappe.call({
					method: "my_visit_monitor.api.check_out_visit",
					args: { visit, latitude: coords.latitude, longitude: coords.longitude, accuracy: coords.accuracy },
				});
			})
			// The check-out is saved.
			.then((r) => {
				// Green confirmation.
				frappe.show_alert({ message: __("Out time updated successfully!"), indicator: "green" });
				// Answer of the server for the caller.
				return r;
			});
	},
};
