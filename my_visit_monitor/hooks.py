# File: hooks.py
# Purpose: Frappe hooks of the app: permission rules and the approval of self-registered logins.
# Created: 2026-10-05
# Last updated: 2026-10-10

app_name = "my_visit_monitor"
app_title = "My Visit Monitor"
app_publisher = "huda"
app_description = "my visit monitor"
app_email = "support03@softworld.co.in"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "my_visit_monitor",
# 		"logo": "/assets/my_visit_monitor/logo.png",
# 		"title": "My Visit Monitor",
# 		"route": "/my_visit_monitor",
# 		"has_permission": "my_visit_monitor.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/my_visit_monitor/css/my_visit_monitor.css"
# app_include_js = "/assets/my_visit_monitor/js/my_visit_monitor.js"

# include js, css files in header of web template
# web_include_css = "/assets/my_visit_monitor/css/my_visit_monitor.css"
# web_include_js = "/assets/my_visit_monitor/js/my_visit_monitor.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "my_visit_monitor/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}

# Reading the phone's position, used by the visit form and by the Check Out button in the visit list.
doctype_js = {"MVM Visit Entry": "public/js/mvm_position.js"}
doctype_list_js = {"MVM Visit Entry": "public/js/mvm_position.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "my_visit_monitor/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "my_visit_monitor.utils.jinja_methods",
# 	"filters": "my_visit_monitor.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "my_visit_monitor.install.before_install"
# after_install = "my_visit_monitor.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "my_visit_monitor.uninstall.before_uninstall"
# after_uninstall = "my_visit_monitor.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "my_visit_monitor.utils.before_app_install"
# after_app_install = "my_visit_monitor.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "my_visit_monitor.utils.before_app_uninstall"
# after_app_uninstall = "my_visit_monitor.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "my_visit_monitor.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "my_visit_monitor.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["my_visit_monitor.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# Limits the customer and visit lists to the records of the logged-in employee.
permission_query_conditions = {
	"MVM Customer": "my_visit_monitor.permission.customer_query_conditions",
	"MVM Visit Entry": "my_visit_monitor.permission.visit_query_conditions",
	# Registrations are only for admins and team managers.
	"MVM Registration": "my_visit_monitor.registration.registration_query_conditions",
	# Employee records: admins all, managers their team, employees their own.
	"MVM Employee": "my_visit_monitor.permission.employee_query_conditions",
}

# The same limits when a single customer or visit is opened.
has_permission = {
	"MVM Customer": "my_visit_monitor.permission.customer_has_permission",
	"MVM Visit Entry": "my_visit_monitor.permission.visit_has_permission",
	"MVM Registration": "my_visit_monitor.registration.registration_has_permission",
	"MVM Employee": "my_visit_monitor.permission.employee_has_permission",
}

# Document Events
# ---------------
# Hook on document methods and events

# A login made through Sign Up gets a registration that waits for an administrator.
doc_events = {
	"User": {
		# No set-password email before approval.
		"before_insert": "my_visit_monitor.registration.on_user_before_insert",
		"after_insert": "my_visit_monitor.registration.on_user_insert",
	},
}

# A self-registered login can only log in after it was approved.
on_login = "my_visit_monitor.registration.check_approval"

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"my_visit_monitor.tasks.all"
# 	],
# 	"daily": [
# 		"my_visit_monitor.tasks.daily"
# 	],
# 	"hourly": [
# 		"my_visit_monitor.tasks.hourly"
# 	],
# 	"weekly": [
# 		"my_visit_monitor.tasks.weekly"
# 	],
# 	"monthly": [
# 		"my_visit_monitor.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "my_visit_monitor.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "my_visit_monitor.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "my_visit_monitor.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "my_visit_monitor.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["my_visit_monitor.utils.before_request"]
# after_request = ["my_visit_monitor.utils.after_request"]

# Job Events
# ----------
# before_job = ["my_visit_monitor.utils.before_job"]
# after_job = ["my_visit_monitor.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"my_visit_monitor.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

