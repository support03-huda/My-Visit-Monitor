"""Dummy data for trying out the app.

bench --site visit-monitor.local execute my_visit_monitor.demo.make
"""

import random

import frappe
from frappe.utils import add_days, today

ZONES = ["West", "North", "South", "East"]

LOCATIONS = [
	("Pune Office", "Pune", "Maharashtra", "411001"),
	("Mumbai Office", "Mumbai", "Maharashtra", "400001"),
	("Delhi Office", "New Delhi", "Delhi", "110001"),
	("Bengaluru Office", "Bengaluru", "Karnataka", "560001"),
]

REASONS = ["Demo", "Follow-up", "Payment Collection", "Support Call", "New Enquiry", "Training"]

# name, email, mobile, location, zones; the first one is the manager of the others
EMPLOYEES = [
	("Support Admin", "support03@softworld.co.in", "9800000001", "Pune Office", ZONES),
	("Amit Kulkarni", "amit.kulkarni@example.com", "9800000002", "Pune Office", ["West"]),
	("Neha Sharma", "neha.sharma@example.com", "9800000003", "Delhi Office", ["North"]),
	("Ravi Iyer", "ravi.iyer@example.com", "9800000004", "Bengaluru Office", ["South"]),
	("Priya Das", "priya.das@example.com", "9800000005", "Mumbai Office", ["West", "East"]),
]

# company, contact, city, state, pincode, zone, latitude, longitude
CUSTOMERS = [
	("Acme Engineering Pvt Ltd", "Suresh Patil", "Pune", "Maharashtra", "411045", "West", 18.5590, 73.7868),
	("Bharat Tools", "Mahesh Joshi", "Pune", "Maharashtra", "411014", "West", 18.5679, 73.9143),
	("Coastal Traders", "Farhan Shaikh", "Mumbai", "Maharashtra", "400072", "West", 19.1176, 72.9060),
	("Deccan Polymers", "Anita Deshmukh", "Nashik", "Maharashtra", "422007", "West", 19.9975, 73.7898),
	("Everest Castings", "Rohit Verma", "New Delhi", "Delhi", "110020", "North", 28.5355, 77.2732),
	("Ganga Steel Works", "Pooja Singh", "Kanpur", "Uttar Pradesh", "208001", "North", 26.4499, 80.3319),
	("Himalaya Pharma", "Vikram Chauhan", "Chandigarh", "Chandigarh", "160017", "North", 30.7333, 76.7794),
	("Kaveri Textiles", "Lakshmi Narayanan", "Coimbatore", "Tamil Nadu", "641001", "South", 11.0168, 76.9558),
	("Malabar Spices", "Thomas Kurian", "Kochi", "Kerala", "682001", "South", 9.9312, 76.2673),
	("Nandi Automation", "Kiran Gowda", "Bengaluru", "Karnataka", "560058", "South", 13.0285, 77.5197),
	("Orient Jute Mills", "Subhash Ghosh", "Kolkata", "West Bengal", "700001", "East", 22.5726, 88.3639),
	("Purvi Packaging", "Ritu Agarwal", "Bhubaneswar", "Odisha", "751001", "East", 20.2961, 85.8245),
]

VISIT_NOTES = [
	"Discussed requirements and shared the product catalogue.",
	"Followed up on the pending quotation.",
	"Collected the outstanding payment cheque.",
	"Resolved the reported issue on site.",
	"Gave a product demo to the purchase team.",
	"Trained two operators on the new setup.",
]

VISITS = 30


def make():
	for zone in ZONES:
		if not frappe.db.exists("MVM Zone", zone):
			frappe.get_doc({"doctype": "MVM Zone", "zone_name": zone}).insert()

	locations = {}
	for name, city, state, pincode in LOCATIONS:
		locations[name] = get_or_create(
			"MVM Location",
			{"location_name": name},
			city=city,
			state=state,
			pincode=pincode,
			country="India",
			address_line_1=f"{random.randint(1, 99)} Main Road",
		)

	reasons = [get_or_create("MVM Visit Reason", {"description": reason}) for reason in REASONS]

	employees = []
	for name, email, mobile, location, zones in EMPLOYEES:
		employees.append(
			get_or_create(
				"MVM Employee",
				{"email": email},
				employee_name=name,
				mobile=mobile,
				location=location.replace(" Office", ""),
				reporting_to=employees[0] if employees else None,
				city=location.replace(" Office", ""),
				country="India",
				zones=[{"zone": zone} for zone in zones],
			)
		)
	manager, field_staff = employees[0], employees[1:]

	def staff_for(zone):
		return [e for e in field_staff if zone in frappe.get_all(
			"MVM Employee Zone", filters={"parent": e}, pluck="zone"
		)] or [manager]

	customers = {}
	for index, (company, contact, city, state, pincode, zone, lat, lng) in enumerate(CUSTOMERS):
		customers[
			get_or_create(
				"MVM Customer",
				{"company_name": company},
				customer_name=contact,
				mobile=f"98220000{index:02d}",
				email=f"contact{index + 1}@example.com",
				followed_by=staff_for(zone)[0],
				reporting_to=manager,
				zone=zone,
				next_followup_days=random.choice([7, 15, 30]),
				address_line_1=f"Plot {random.randint(1, 250)}, Industrial Area",
				address_line_2=f"Phase {random.randint(1, 4)}",
				city=city,
				state=state,
				pincode=pincode,
				country="India",
			)
		] = (zone, lat, lng)

	created_visits = 0
	if not frappe.db.count("MVM Visit Entry"):
		created_visits = make_visits(customers, staff_for, reasons)

	frappe.db.commit()
	print(
		f"Zones: {len(ZONES)}, Locations: {len(locations)}, Reasons: {len(reasons)}, "
		f"Employees: {len(employees)}, Customers: {len(customers)}, Visits created: {created_visits}"
	)


def get_or_create(doctype, key, **values):
	name = frappe.db.get_value(doctype, key)
	if name:
		return name
	return frappe.get_doc({"doctype": doctype, **key, **values}).insert().name


def make_visits(customers, staff_for, reasons):
	"""Visits over the last 30 days; today's are still checked in."""
	for index in range(VISITS):
		customer = random.choice(list(customers))
		zone, lat, lng = customers[customer]
		days_ago = 0 if index < 4 else random.randint(1, 30)

		visit = frappe.get_doc(
			{
				"doctype": "MVM Visit Entry",
				"customer": customer,
				"visit_reason": random.choice(reasons),
				"description": random.choice(VISIT_NOTES),
				"employee": random.choice(staff_for(zone)),
				# a point within a few hundred metres of the customer
				"checkin_latitude": lat + random.uniform(-0.002, 0.002),
				"checkin_longitude": lng + random.uniform(-0.002, 0.002),
			}
		).insert()

		if not days_ago:
			continue

		# check-in is always stamped with the current time, so move finished visits into the past
		hour = random.randint(9, 16)
		visit_date = add_days(today(), -days_ago)
		followup_days = frappe.db.get_value("MVM Customer", customer, "next_followup_days")
		visit.db_set(
			{
				"status": "Checked Out",
				"checkin_date": visit_date,
				"checkin_time": f"{hour:02d}:{random.randint(0, 59):02d}:00",
				"checkout_date": visit_date,
				"checkout_time": f"{hour + 1:02d}:{random.randint(0, 59):02d}:00",
				"checkout_latitude": visit.checkin_latitude,
				"checkout_longitude": visit.checkin_longitude,
				"next_visit_date": add_days(visit_date, followup_days) if followup_days else None,
			}
		)
	return VISITS
