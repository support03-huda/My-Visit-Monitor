// File: mvm_dashboard.js
// Purpose: Visit Dashboard page: work figures of an employee for a month, quarter or year (for appraisals),
//          month calendar (worked days green, weekend shaded), daily attendance list with customer names, top 10 customers, and for managers the top 10 employees,
//          the top 10 customers overall and the comparison of all employees. The sections are shown in tabs
//          (Overview, Attendance, Customers, Team) and every list can be exported as CSV.
// Created: 2026-10-09
// Last updated: 2026-10-10

// Names of the week days, Monday first, as shown above the calendar.
const MVM_WEEK_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
// Short names of the months, for titles and chart labels.
const MVM_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// Period types and how many months each one covers.
const MVM_PERIODS = { Month: 1, Quarter: 3, Year: 12 };
// First month of the appraisal year (April).
const MVM_YEAR_START = 4;

// Look of the dashboard; the colours also work in dark mode.
const MVM_DASHBOARD_STYLE = `
	.mvm-dashboard { max-width: 1100px; margin: 0 auto; padding: 16px 0; }
	.mvm-dashboard h5 { margin: 24px 0 12px; }
	.mvm-dashboard h5.mvm-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
	.mvm-dashboard .mvm-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
	.mvm-dashboard .mvm-name { font-size: 20px; font-weight: 600; }
	.mvm-dashboard .mvm-nav { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
	.mvm-dashboard .mvm-title { min-width: 170px; text-align: center; font-weight: 600; }
	.mvm-dashboard .mvm-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
	.mvm-dashboard .mvm-tile { padding: 12px; border: 1px solid var(--border-color); border-radius: 8px; }
	.mvm-dashboard .mvm-tile-value { font-size: 24px; font-weight: 600; }
	.mvm-dashboard .mvm-tile-label { font-size: 12px; color: var(--text-muted); }
	.mvm-dashboard .mvm-tile-note { font-size: 11px; color: var(--text-muted); }
	.mvm-dashboard .mvm-tabs { display: flex; flex-wrap: wrap; gap: 4px; margin: 20px 0 4px; border-bottom: 1px solid var(--border-color); }
	.mvm-dashboard .mvm-tab { padding: 8px 16px; cursor: pointer; color: var(--text-muted); border-bottom: 2px solid transparent; margin-bottom: -1px; }
	.mvm-dashboard .mvm-tab.mvm-active { color: var(--text-color); font-weight: 600; border-bottom-color: var(--primary); }
	.mvm-dashboard .mvm-charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }
	.mvm-dashboard .mvm-bars { display: flex; align-items: flex-end; gap: 6px; height: 180px; }
	.mvm-dashboard .mvm-bar { flex: 1; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; height: 100%; min-width: 0; }
	.mvm-dashboard .mvm-bar-value { font-size: 11px; }
	.mvm-dashboard .mvm-bar-fill { width: 100%; min-height: 2px; border-radius: 4px 4px 0 0; background: rgba(128, 128, 128, 0.45); }
	.mvm-dashboard .mvm-bar.mvm-selected .mvm-bar-fill { background: #2f9e44; }
	.mvm-dashboard .mvm-bar-label { font-size: 10px; color: var(--text-muted); white-space: nowrap; }
	.mvm-dashboard .mvm-reason { display: grid; grid-template-columns: minmax(90px, 35%) 1fr 70px; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; }
	.mvm-dashboard .mvm-reason-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.mvm-dashboard .mvm-reason-track { height: 12px; border-radius: 6px; background: rgba(128, 128, 128, 0.18); }
	.mvm-dashboard .mvm-reason-fill { height: 100%; border-radius: 6px; background: #2f9e44; }
	.mvm-dashboard .mvm-reason-count { text-align: right; color: var(--text-muted); }
	.mvm-dashboard .mvm-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; margin-bottom: 8px; }
	.mvm-dashboard .mvm-weekday { text-align: center; font-size: 12px; color: var(--text-muted); padding: 4px 0; }
	.mvm-dashboard .mvm-day { min-height: 64px; padding: 6px 8px; border: 1px solid var(--border-color); border-radius: 6px; }
	.mvm-dashboard .mvm-day.mvm-empty { border-color: transparent; }
	.mvm-dashboard .mvm-day.mvm-weekend { background: rgba(128, 128, 128, 0.18); }
	.mvm-dashboard .mvm-day.mvm-worked { background: rgba(47, 158, 68, 0.3); border-color: #2f9e44; cursor: pointer; }
	.mvm-dashboard .mvm-day.mvm-today { outline: 2px solid var(--primary); outline-offset: -2px; }
	.mvm-dashboard .mvm-day-number { font-weight: 600; }
	.mvm-dashboard .mvm-day-note { font-size: 11px; color: var(--text-muted); }
	.mvm-dashboard .mvm-legend { display: flex; flex-wrap: wrap; gap: 16px; font-size: 12px; color: var(--text-muted); }
	.mvm-dashboard .mvm-swatch { display: inline-block; width: 12px; height: 12px; border-radius: 3px; border: 1px solid var(--border-color); vertical-align: -1px; margin-right: 4px; }
	.mvm-dashboard .mvm-table-wrap { overflow-x: auto; }
	.mvm-dashboard .mvm-table td.mvm-number, .mvm-dashboard .mvm-table th.mvm-number { text-align: right; }
	.mvm-dashboard .mvm-table tr.mvm-weekend td { background: rgba(128, 128, 128, 0.12); }
	.mvm-dashboard .mvm-table tr.mvm-worked td:first-child { box-shadow: inset 3px 0 0 #2f9e44; }
	.mvm-dashboard .mvm-table tr.mvm-current td { font-weight: 600; }
	.mvm-dashboard .mvm-table tr[data-employee] { cursor: pointer; }
`;

// Two digits, for dates.
function mvm_pad(number) {
	// 5 becomes 05.
	return String(number).padStart(2, "0");
}

// A date as YYYY-MM-DD, the way the server sends and expects it.
function mvm_date(year, month, day) {
	// Year, month and day joined by dashes.
	return `${year}-${mvm_pad(month)}-${mvm_pad(day)}`;
}

// Number of days in a month (month 1 to 12).
function mvm_days_in_month(year, month) {
	// Day 0 of the next month is the last day of this month.
	return new Date(year, month, 0).getDate();
}

// Week day of a date with Monday = 0 ... Sunday = 6.
function mvm_weekday(year, month, day) {
	// JavaScript counts from Sunday = 0, so shift by one.
	return (new Date(year, month - 1, day).getDay() + 6) % 7;
}

// A share as a whole percentage; a dash when there is nothing to divide by.
function mvm_percent(part, whole) {
	// Never more than 100 %.
	return whole ? `${Math.min(100, Math.round((part / whole) * 100))}%` : "-";
}

// Heading of a list with an Export button; `name` becomes the first part of the file name.
function mvm_heading(title, name) {
	// The title on the left, the button on the right.
	return `<h5 class="mvm-heading"><span>${title}</span><button class="btn btn-default btn-xs" data-export="${name}">${__("Export")}</button></h5>`;
}

// Rows of texts as CSV text that Excel opens directly.
function mvm_csv(rows) {
	// One line per row.
	return rows
		.map((row) =>
			row
				.map((cell) => {
					// The cell as text.
					let text = String(cell == null ? "" : cell);
					// A text starting with = + or @ would be run as a formula by Excel, so make it plain text.
					if (/^[=+@]/.test(text)) text = "'" + text;
					// Quoted, with quotes inside doubled.
					return `"${text.replace(/"/g, '""')}"`;
				})
				// Cells are separated by commas.
				.join(",")
		)
		// Lines end the way Excel expects.
		.join("\r\n");
}

// Let the browser save a text as a file.
function mvm_download(filename, text) {
	// The file content; the first character tells Excel the text is UTF-8.
	const blob = new Blob(["\ufeff" + text], { type: "text/csv;charset=utf-8;" });
	// Temporary address of that content.
	const url = URL.createObjectURL(blob);
	// Invisible link to that address.
	const link = document.createElement("a");
	// Where the link points.
	link.href = url;
	// Name of the saved file.
	link.download = filename;
	// The link must be on the page for the click to work in every browser.
	document.body.appendChild(link);
	// Start the download.
	link.click();
	// Remove the link again.
	link.remove();
	// Free the temporary address.
	URL.revokeObjectURL(url);
}

// Frappe calls this once, the first time the page is opened.
frappe.pages["mvm-dashboard"].on_page_load = function (wrapper) {
	// Standard page frame with the title bar.
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Visit Dashboard"),
		single_column: true,
	});
	// Add the styles of the dashboard to the page.
	$(`<style>${MVM_DASHBOARD_STYLE}</style>`).appendTo(page.main);
	// Container everything is drawn into.
	const $body = $('<div class="mvm-dashboard"></div>').appendTo(page.main);

	// Today, to start on the current month.
	const now = new Date();
	// What the page is showing: employee, period type, a month inside the period and the open tab.
	const state = { employee: null, type: "Month", year: now.getFullYear(), month: now.getMonth() + 1, tab: "overview" };
	// The figures and the period drawn last; used when only the tab changes.
	let last = null;

	// Employee selector in the bar under the title.
	const employee_field = page.add_field({
		fieldname: "employee",
		label: __("Employee"),
		fieldtype: "Link",
		options: "MVM Employee",
		// Runs when another employee is picked.
		change() {
			// The employee now in the field.
			const value = employee_field.get_value() || null;
			// Nothing changed (the page itself filled the field).
			if (value === state.employee) return;
			// Remember the new employee.
			state.employee = value;
			// Show that employee.
			load();
		},
	});

	// The months of the period being shown, with its first day, last day and title.
	function get_period() {
		// Number of months in the period.
		const length = MVM_PERIODS[state.type];
		// Months counted from year 0, to move across years easily.
		let first = state.year * 12 + (state.month - 1);
		// A quarter starts in January, April, July or October.
		if (state.type === "Quarter") first -= first % 3;
		// The appraisal year starts in April.
		if (state.type === "Year") first -= (first - (MVM_YEAR_START - 1) + 12) % 12;
		// One entry per month of the period.
		const months = [];
		// First month up to the last month.
		for (let index = first; index < first + length; index++) {
			// Year and month (1 to 12) of that entry.
			months.push({ year: Math.floor(index / 12), month: (index % 12) + 1 });
		}
		// First and last month of the period.
		const from = months[0];
		const to = months[months.length - 1];
		// Title: "Oct 2026" for a month, "Apr 2026 - Mar 2027" for a longer period.
		const title =
			length === 1
				? `${__(MVM_MONTHS[from.month - 1])} ${from.year}`
				: `${__(MVM_MONTHS[from.month - 1])} ${from.year} - ${__(MVM_MONTHS[to.month - 1])} ${to.year}`;
		// Everything the page needs to know about the period.
		return {
			months,
			title,
			start: mvm_date(from.year, from.month, 1),
			end: mvm_date(to.year, to.month, mvm_days_in_month(to.year, to.month)),
		};
	}

	// Ask the server for the figures of the period and draw them.
	function load() {
		// Period being shown.
		const period = get_period();
		// Server method in api.py.
		frappe
			.call({
				method: "my_visit_monitor.api.get_dashboard",
				args: { employee: state.employee, start: period.start, end: period.end },
			})
			// The server answered.
			.then((r) => {
				// Figures of the employee and, for managers, of all employees.
				const data = r.message;
				// The server decides whose figures are shown (field staff: always their own).
				state.employee = data.employee;
				// Show that employee in the selector.
				employee_field.set_value(data.employee || "");
				// Field staff cannot pick another employee; admins and team managers can.
				employee_field.df.read_only = data.can_compare ? 0 : 1;
				// A team manager may only pick the members of the team.
				employee_field.get_query = () =>
					data.team_members ? { filters: { name: ["in", data.team_members] } } : {};
				// Apply the read-only setting.
				employee_field.refresh();
				// Draw the page.
				render(data, period);
			});
	}

	// Move one period back (-1) or forward (+1).
	function shift_period(step) {
		// Months counted from year 0, moved by the length of the period.
		const index = state.year * 12 + (state.month - 1) + step * MVM_PERIODS[state.type];
		// Year of the new month.
		state.year = Math.floor(index / 12);
		// New month (1 to 12).
		state.month = (index % 12) + 1;
		// Show it.
		load();
	}

	// Open the visits of one day in the visit list.
	function open_visits(date) {
		// Visit list filtered on the employee and the check-in date.
		frappe.set_route("List", "MVM Visit Entry", { employee: state.employee, checkin_date: date });
	}

	// The days of one month with what the employee did on each.
	function get_days(data, year, month) {
		// One entry per day of the month.
		const days = [];
		// Day 1 up to the last day.
		for (let number = 1; number <= mvm_days_in_month(year, month); number++) {
			// Date as YYYY-MM-DD.
			const date = mvm_date(year, month, number);
			// Week day with Monday = 0 ... Sunday = 6.
			const weekday = mvm_weekday(year, month, number);
			// Everything the calendar and the lists need for this day.
			days.push({
				number,
				date,
				weekday,
				// Visits of that day; undefined when there was none.
				work: (data.days || {})[date],
				// Saturday or Sunday.
				weekend: weekday >= 5,
				// The day is still to come.
				future: date > data.today,
				// The day is today.
				today: date === data.today,
			});
		}
		// Days of the month.
		return days;
	}

	// The boxes with the main figures of the period.
	function render_tiles(data) {
		// Figures of the employee; zeros when no employee is selected.
		const summary = data.summary || {};
		// Label, value and a small note for every box.
		const tiles = [
			[__("Visits"), summary.visits || 0, ""],
			[__("Days worked"), summary.days_worked || 0, __("of {0} working days", [data.working_days])],
			[__("Attendance"), mvm_percent(summary.weekdays_worked || 0, data.working_days), __("Mon to Fri worked")],
			[
				__("Visits per day"),
				summary.days_worked ? (summary.visits / summary.days_worked).toFixed(1) : "-",
				__("on days worked"),
			],
			[__("Customers visited"), summary.customers || 0, __("{0} new", [data.new_customers || 0])],
			[
				__("Coverage"),
				mvm_percent(summary.covered || 0, summary.allocated || 0),
				__("{0} of {1} allocated customers", [summary.covered || 0, summary.allocated || 0]),
			],
		];
		// One box per figure.
		return `<div class="mvm-tiles">${tiles
			.map(
				([label, value, note]) => `<div class="mvm-tile">
					<div class="mvm-tile-value">${value}</div>
					<div class="mvm-tile-label">${label}</div>
					<div class="mvm-tile-note">${note}</div>
				</div>`
			)
			.join("")}</div>`;
	}

	// Bar chart of the visits in each of the last 12 months; the months of the period are green.
	function render_trend(data, period) {
		// Months of the chart, oldest first.
		const trend = data.trend || [];
		// Highest bar, to scale the others; at least 1 to avoid dividing by zero.
		const highest = Math.max(1, ...trend.map((entry) => entry.visits));
		// Months of the period as YYYY-MM, to highlight them.
		const selected = period.months.map((entry) => `${entry.year}-${mvm_pad(entry.month)}`);
		// One bar per month.
		const bars = trend
			.map((entry) => {
				// Year and month of the bar.
				const [year, month] = entry.month.split("-");
				// Height of the bar as a percentage of the highest one.
				const height = Math.round((entry.visits / highest) * 100);
				// The bar with its value above and the month below.
				return `<div class="mvm-bar ${selected.includes(entry.month) ? "mvm-selected" : ""}"
						title="${__("{0} visits on {1} days", [entry.visits, entry.days_worked])}">
					<div class="mvm-bar-value">${entry.visits || ""}</div>
					<div class="mvm-bar-fill" style="height: ${height}%;"></div>
					<div class="mvm-bar-label">${__(MVM_MONTHS[Number(month) - 1])} ${year.slice(2)}</div>
				</div>`;
			})
			.join("");
		// The chart with its heading.
		return `<div><h5>${__("Visits per Month")}</h5><div class="mvm-bars">${bars}</div></div>`;
	}

	// Visits per reason as horizontal bars.
	function render_reasons(data) {
		// Reasons, most used first.
		const reasons = data.reasons || [];
		// All visits, for the percentages.
		const total = reasons.reduce((sum, entry) => sum + entry.visits, 0);
		// One line per reason.
		const lines = reasons
			.map(
				(entry) => `<div class="mvm-reason">
					<div class="mvm-reason-name">${frappe.utils.escape_html(entry.reason || __("No reason"))}</div>
					<div class="mvm-reason-track"><div class="mvm-reason-fill" style="width: ${Math.round((entry.visits / total) * 100)}%;"></div></div>
					<div class="mvm-reason-count">${entry.visits} (${mvm_percent(entry.visits, total)})</div>
				</div>`
			)
			.join("");
		// The lines with their heading; a note when there are no visits.
		return `<div><h5>${__("Visits by Reason")}</h5>${lines || `<div class="text-muted">${__("No visits in this period.")}</div>`}</div>`;
	}

	// The calendar of one month: worked days green, Saturday and Sunday shaded.
	function render_calendar(days) {
		// Empty cells before day 1, so day 1 lands under its week day.
		const blanks = '<div class="mvm-day mvm-empty"></div>'.repeat(days[0].weekday);
		// One cell per day.
		const cells = days
			.map((day) => {
				// Green when worked, shaded on a free weekend day, outlined today.
				const classes = [
					"mvm-day",
					day.work ? "mvm-worked" : "",
					!day.work && day.weekend ? "mvm-weekend" : "",
					day.today ? "mvm-today" : "",
				].join(" ");
				// Number of visits under the day number.
				const note = day.work ? __("{0} visit(s)", [day.work.visits]) : "";
				// The cell; a worked day remembers its date for the click.
				return `<div class="${classes}" ${day.work ? `data-date="${day.date}"` : ""}>
					<div class="mvm-day-number">${day.number}</div>
					<div class="mvm-day-note">${note}</div>
				</div>`;
			})
			.join("");
		// Heading, week day names, cells and the legend.
		return `<h5>${__("Calendar")}</h5>
			<div class="mvm-grid">
				${MVM_WEEK_DAYS.map((label) => `<div class="mvm-weekday">${__(label)}</div>`).join("")}
				${blanks}${cells}
			</div>
			<div class="mvm-legend">
				<span><span class="mvm-swatch" style="background: rgba(47, 158, 68, 0.3); border-color: #2f9e44;"></span>${__("Worked")}</span>
				<span><span class="mvm-swatch" style="background: rgba(128, 128, 128, 0.18);"></span>${__("Saturday / Sunday")}</span>
				<span><span class="mvm-swatch"></span>${__("No visit")}</span>
			</div>`;
	}

	// The daily attendance list of one month.
	function render_attendance(days) {
		// One row per day.
		const rows = days
			.map((day) => {
				// Present when worked; else Weekend, nothing for a future day, or Absent.
				const status = day.work
					? `<span class="indicator-pill green">${__("Present")}</span>`
					: day.weekend
					? `<span class="indicator-pill gray">${__("Weekend")}</span>`
					: day.future
					? ""
					: `<span class="indicator-pill red">${__("Absent")}</span>`;
				// Names of the customers visited that day, separated by commas.
				const names = day.work ? frappe.utils.escape_html((day.work.customer_names || []).join(", ")) : "";
				// The row: date, week day, status, first check-in, last check-out, visits, customers, their names.
				return `<tr class="${day.work ? "mvm-worked" : day.weekend ? "mvm-weekend" : ""}">
					<td>${frappe.datetime.str_to_user(day.date)}</td>
					<td>${__(MVM_WEEK_DAYS[day.weekday])}</td>
					<td>${status}</td>
					<td>${day.work ? day.work.first_in : ""}</td>
					<td>${day.work ? day.work.last_out : ""}</td>
					<td class="mvm-number">${day.work ? `<a data-date="${day.date}">${day.work.visits}</a>` : ""}</td>
					<td class="mvm-number">${day.work ? day.work.customers : ""}</td>
					<td>${names}</td>
				</tr>`;
			})
			.join("");
		// Heading and table.
		return `${mvm_heading(__("Daily Attendance"), "daily-attendance")}
			<div class="mvm-table-wrap">
				<table class="table table-bordered mvm-table">
					<thead>
						<tr>
							<th>${__("Date")}</th>
							<th>${__("Day")}</th>
							<th>${__("Status")}</th>
							<th>${__("First Check-in")}</th>
							<th>${__("Last Check-out")}</th>
							<th class="mvm-number">${__("Visits")}</th>
							<th class="mvm-number">${__("Customers (per day)")}</th>
							<th>${__("Customer Names")}</th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
			</div>`;
	}

	// One line per month, for a quarter or a year.
	function render_months(data, period) {
		// One row per month of the period.
		const rows = period.months
			.map((entry) => {
				// Days of that month.
				const days = get_days(data, entry.year, entry.month);
				// Monday to Friday, up to today.
				const working = days.filter((day) => !day.weekend && !day.future).length;
				// Days with at least one visit.
				const worked = days.filter((day) => day.work);
				// Monday to Friday with at least one visit.
				const weekdays = worked.filter((day) => !day.weekend).length;
				// Visits in that month.
				const visits = worked.reduce((sum, day) => sum + day.work.visits, 0);
				// The row: month, working days, days worked, attendance, visits, visits per day.
				return `<tr>
					<td>${__(MVM_MONTHS[entry.month - 1])} ${entry.year}</td>
					<td class="mvm-number">${working}</td>
					<td class="mvm-number">${worked.length}</td>
					<td class="mvm-number">${mvm_percent(weekdays, working)}</td>
					<td class="mvm-number">${visits}</td>
					<td class="mvm-number">${worked.length ? (visits / worked.length).toFixed(1) : "-"}</td>
				</tr>`;
			})
			.join("");
		// Heading and table.
		return `${mvm_heading(__("Month by Month"), "month-by-month")}
			<div class="mvm-table-wrap">
				<table class="table table-bordered mvm-table">
					<thead>
						<tr>
							<th>${__("Month")}</th>
							<th class="mvm-number">${__("Working Days")}</th>
							<th class="mvm-number">${__("Days Worked")}</th>
							<th class="mvm-number">${__("Attendance")}</th>
							<th class="mvm-number">${__("Visits")}</th>
							<th class="mvm-number">${__("Visits per Day")}</th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
			</div>`;
	}

	// Allocated customers the employee did not visit in the period.
	function render_not_visited(data) {
		// Nothing to show when every allocated customer was visited.
		if (!data.not_visited_count) return "";
		// One row per customer.
		const rows = data.not_visited
			.map(
				(customer) => `<tr>
					<td><a href="/app/mvm-customer/${encodeURIComponent(customer.name)}">${frappe.utils.escape_html(customer.company_name || customer.name)}</a></td>
					<td>${frappe.utils.escape_html(customer.city || "")}</td>
					<td>${frappe.utils.escape_html(customer.zone || "")}</td>
					<td>${customer.last_visit ? frappe.datetime.str_to_user(customer.last_visit) : __("Never")}</td>
				</tr>`
			)
			.join("");
		// Note when the list was cut short.
		const more =
			data.not_visited_count > data.not_visited.length
				? `<div class="text-muted">${__("Showing the first {0}.", [data.not_visited.length])}</div>`
				: "";
		// Heading with the number of customers, and the table.
		return `${mvm_heading(__("Allocated Customers Not Visited ({0})", [data.not_visited_count]), "customers-not-visited")}
			<div class="mvm-table-wrap">
				<table class="table table-bordered mvm-table">
					<thead>
						<tr>
							<th>${__("Customer")}</th>
							<th>${__("City")}</th>
							<th>${__("Zone")}</th>
							<th>${__("Last Visit")}</th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
			</div>${more}`;
	}

	// Comparison of all employees for the period (managers only).
	function render_team(data) {
		// Field staff get no comparison.
		if (!data.team) return "";
		// One row per employee, the one with the most visits first.
		const rows = data.team
			.map(
				(row, index) => `<tr data-employee="${frappe.utils.escape_html(row.employee)}" class="${row.employee === data.employee ? "mvm-current" : ""}">
					<td class="mvm-number">${index + 1}</td>
					<td>${frappe.utils.escape_html(row.employee_name)}</td>
					<td class="mvm-number">${row.visits}</td>
					<td class="mvm-number">${row.days_worked}</td>
					<td class="mvm-number">${mvm_percent(row.weekdays_worked, data.working_days)}</td>
					<td class="mvm-number">${row.days_worked ? (row.visits / row.days_worked).toFixed(1) : "-"}</td>
					<td class="mvm-number">${row.customers}</td>
					<td class="mvm-number">${mvm_percent(row.covered, row.allocated)}</td>
				</tr>`
			)
			.join("");
		// Heading and table.
		return `${mvm_heading(__("All Employees"), "all-employees")}
			<div class="mvm-table-wrap">
				<table class="table table-bordered mvm-table">
					<thead>
						<tr>
							<th class="mvm-number">${__("Rank")}</th>
							<th>${__("Employee")}</th>
							<th class="mvm-number">${__("Visits")}</th>
							<th class="mvm-number">${__("Days Worked")}</th>
							<th class="mvm-number">${__("Attendance")}</th>
							<th class="mvm-number">${__("Visits per Day")}</th>
							<th class="mvm-number">${__("Customers")}</th>
							<th class="mvm-number">${__("Coverage")}</th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
			</div>`;
	}

	// A top 10 list of customers; `everybody` adds the number of employees who visited each one.
	function render_top_customers(rows, title, name, everybody) {
		// Field staff get no list of all employees.
		if (!rows) return "";
		// Without visits there is nothing to rank.
		if (!rows.length) return `<h5>${title}</h5><div class="text-muted">${__("No visits in this period.")}</div>`;
		// One row per customer, the one with the most visits first.
		const lines = rows
			.map(
				(row, index) => `<tr>
					<td class="mvm-number">${index + 1}</td>
					<td><a href="/app/mvm-customer/${encodeURIComponent(row.customer)}">${frappe.utils.escape_html(row.customer_name || row.customer)}</a></td>
					<td class="mvm-number">${row.visits}</td>
					<td class="mvm-number">${row.days}</td>
					${everybody ? `<td class="mvm-number">${row.employees}</td>` : ""}
					<td>${row.last_visit ? frappe.datetime.str_to_user(row.last_visit) : ""}</td>
				</tr>`
			)
			.join("");
		// Heading with the Export button, and the table.
		return `${mvm_heading(title, name)}
			<div class="mvm-table-wrap">
				<table class="table table-bordered mvm-table">
					<thead>
						<tr>
							<th class="mvm-number">${__("Rank")}</th>
							<th>${__("Customer")}</th>
							<th class="mvm-number">${__("Visits")}</th>
							<th class="mvm-number">${__("Days Visited")}</th>
							${everybody ? `<th class="mvm-number">${__("Employees")}</th>` : ""}
							<th>${__("Last Visit")}</th>
						</tr>
					</thead>
					<tbody>${lines}</tbody>
				</table>
			</div>`;
	}

	// The ten employees with the most visits, as horizontal bars (managers only).
	function render_top_employees(data) {
		// Field staff get no comparison.
		if (!data.team) return "";
		// The first ten of the ranking that have visits at all.
		const top = data.team.filter((row) => row.visits).slice(0, 10);
		// Without visits there is nothing to rank.
		if (!top.length) return `<h5>${__("Top 10 Employees by Visits")}</h5><div class="text-muted">${__("No visits in this period.")}</div>`;
		// The longest bar belongs to the first one.
		const highest = top[0].visits;
		// One bar per employee; a click shows that employee.
		const lines = top
			.map(
				(row, index) => `<div class="mvm-reason" data-employee="${frappe.utils.escape_html(row.employee)}" style="cursor: pointer;">
					<div class="mvm-reason-name">${index + 1}. ${frappe.utils.escape_html(row.employee_name)}</div>
					<div class="mvm-reason-track"><div class="mvm-reason-fill" style="width: ${Math.round((row.visits / highest) * 100)}%;"></div></div>
					<div class="mvm-reason-count">${row.visits}</div>
				</div>`
			)
			.join("");
		// Heading and bars.
		return `<h5>${__("Top 10 Employees by Visits")}</h5>${lines}`;
	}

	// Draw the whole page.
	function render(data, period) {
		// Name shown at the top; a hint when no employee is selected.
		const name = data.employee
			? `${frappe.utils.escape_html(data.employee_name || "")} <span class="text-muted">(${frappe.utils.escape_html(data.employee)})</span>`
			: __("Select an employee");
		// Buttons to switch between month, quarter and year; the active one is highlighted.
		const types = Object.keys(MVM_PERIODS)
			.map(
				(type) =>
					`<button class="btn btn-sm ${type === state.type ? "btn-primary" : "btn-default"}" data-type="${type}">${__(type)}</button>`
			)
			.join("");
		// A month shows the calendar and the daily list; a longer period shows one line per month.
		const detail =
			state.type === "Month"
				? render_calendar(get_days(data, state.year, state.month)) +
				  render_attendance(get_days(data, state.year, state.month))
				: render_months(data, period);

		// Remember what is shown, so a click on a tab can redraw without asking the server again.
		last = { data, period };
		// Key, label and content of every tab.
		const tabs = [
			// Charts: visits per month and visits by reason.
			["overview", __("Overview"), `<div class="mvm-charts">${render_trend(data, period)}${render_reasons(data)}</div>`],
			// Calendar and daily list, or one line per month.
			["attendance", __("Attendance"), detail],
			// Customers visited most and allocated customers not visited.
			[
				"customers",
				__("Customers"),
				(data.employee ? render_top_customers(data.top_customers || [], __("Top 10 Customers"), "top-customers", false) : "") +
					render_not_visited(data),
			],
		];
		// Managers get one more tab with all employees.
		if (data.team) {
			// Top 10 employees, top 10 customers overall and the full ranking.
			tabs.push([
				"team",
				__("Team"),
				render_top_employees(data) +
					render_top_customers(data.team_top_customers, __("Top 10 Customers - All Employees"), "top-customers-all", true) +
					render_team(data),
			]);
		}
		// Fall back to the first tab when the remembered one is not there (field staff have no Team tab).
		if (!tabs.some(([key]) => key === state.tab)) state.tab = "overview";

		// Put the header, the figures, the tab bar and the active tab on the page.
		$body.html(`
			<div class="mvm-head">
				<div class="mvm-name">${name}</div>
				<div class="mvm-nav">
					${types}
					<button class="btn btn-default btn-sm mvm-prev">&lsaquo;</button>
					<div class="mvm-title">${period.title}</div>
					<button class="btn btn-default btn-sm mvm-next">&rsaquo;</button>
				</div>
			</div>
			${render_tiles(data)}
			<div class="mvm-tabs">
				${tabs
					.map(
						([key, label]) =>
							`<div class="mvm-tab ${key === state.tab ? "mvm-active" : ""}" data-tab="${key}">${label}</div>`
					)
					.join("")}
			</div>
			${tabs.find(([key]) => key === state.tab)[2]}
		`);

		// Previous period.
		$body.find(".mvm-prev").on("click", () => shift_period(-1));
		// Next period.
		$body.find(".mvm-next").on("click", () => shift_period(1));
		// A click on a tab shows that tab.
		$body.find("[data-tab]").on("click", (event) => {
			// The tab that was clicked.
			state.tab = $(event.currentTarget).attr("data-tab");
			// Redraw with the figures already loaded.
			render(last.data, last.period);
		});
		// Switch between month, quarter and year.
		$body.find("[data-type]").on("click", (event) => {
			// The type on the button that was clicked.
			state.type = $(event.currentTarget).attr("data-type");
			// Show that period.
			load();
		});
		// A green day or a visit count opens the visits of that day.
		$body.find("[data-date]").on("click", (event) => open_visits($(event.currentTarget).attr("data-date")));
		// An Export button saves the list under it as a CSV file.
		$body.find("[data-export]").on("click", (event) => {
			// The button that was clicked.
			const $button = $(event.currentTarget);
			// Which list it belongs to.
			const name = $button.attr("data-export");
			// The table that follows the heading of the button.
			const $table = $button.closest("h5").nextAll(".mvm-table-wrap").first().find("table");
			// The text of every cell, row by row, headings included.
			const rows = $table
				.find("tr")
				.toArray()
				.map((row) =>
					$(row)
						.find("th, td")
						.toArray()
						.map((cell) => $(cell).text().trim())
				);
			// The comparison is about everybody; the other lists are about one employee.
			const who = name.includes("all") ? "all" : state.employee || "none";
			// For example daily-attendance_A00001_2026-10-01_2026-10-31.csv
			mvm_download(`${name}_${who}_${period.start}_${period.end}.csv`, mvm_csv(rows));
		});
		// A row of the comparison shows that employee.
		$body.find("[data-employee]").on("click", (event) => {
			// Putting the employee in the selector reloads the page for them.
			employee_field.set_value($(event.currentTarget).attr("data-employee"));
		});
	}

	// Show the current month when the page opens.
	load();
};
