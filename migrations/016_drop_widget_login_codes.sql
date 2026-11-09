-- The widget's "Open Savings" no longer logs the browser in (it just opens the site; the browser
-- uses its own login cookie), so its one-time login codes go.
DROP TABLE IF EXISTS widget_login_codes;
