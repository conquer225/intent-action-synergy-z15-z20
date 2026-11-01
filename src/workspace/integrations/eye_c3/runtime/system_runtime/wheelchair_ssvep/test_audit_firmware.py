import unittest

from audit_firmware import ROUTES, audit_car_page, car_requests


class CarPageTests(unittest.TestCase):
    def test_one_line_page_includes_stop_and_post_methods(self):
        buttons = ''.join(
            f'''<button onclick='fetch("{route}",{{method:"POST"}}).then(()=>location.reload())'>go</button>'''
            for route in ROUTES)
        payload = f'<html><h1>ESP32-C3 Car</h1>{buttons}</html>'.encode()
        result = audit_car_page(payload)
        calls = result['allowlisted_javascript_calls']
        self.assertEqual([call['route'] for call in calls], list(ROUTES))
        self.assertTrue(all(call['method'] == 'POST' for call in calls))
        self.assertTrue(all(call['event'] == 'onclick' for call in calls))
        behavior = result['embedded_car_client_behavior']
        self.assertFalse(behavior['release_stop_handler_present'])
        self.assertFalse(behavior['periodic_timer_token_present'])
        self.assertFalse(behavior['receiver_deadman_verified'])

    def test_omitted_options_default_to_get(self):
        self.assertEqual(car_requests("fetch('/stop')", 'onclick')[0]['method'], 'GET')

    def test_single_quoted_post_and_html_entities(self):
        payload = b'''<html>ESP32-C3 Car<button onclick="fetch(&quot;/stop&quot;, {method:'post'})">stop</button></html>'''
        calls = audit_car_page(payload)['allowlisted_javascript_calls']
        self.assertEqual(calls[0]['method'], 'POST')

    def test_dynamic_method_is_not_assumed_to_be_get(self):
        self.assertEqual(car_requests('fetch("/start", {method:verb})', 'onclick')[0]['method'], 'unspecified')
        self.assertEqual(car_requests('fetch("/start", options)', 'onclick'), [])

    def test_nonallowlisted_route_is_not_emitted(self):
        self.assertEqual(car_requests('fetch("/wifi?password=secret", {method:"POST"})', 'onclick'), [])

    def test_release_stop_and_timer_are_distinct_evidence(self):
        payload = b'''<html>ESP32-C3 Car<button onpointerup='fetch("/stop", {method:"POST"})'>stop</button><script>setInterval(poll, 100);</script></html>'''
        behavior = audit_car_page(payload)['embedded_car_client_behavior']
        self.assertTrue(behavior['release_stop_handler_present'])
        self.assertTrue(behavior['periodic_timer_token_present'])
        self.assertFalse(behavior['receiver_deadman_verified'])

    def test_external_scripts_require_separate_inspection(self):
        payload = b'<html>ESP32-C3 Car<script src="/control.js"></script></html>'
        self.assertEqual(audit_car_page(payload)['embedded_car_client_behavior']['external_script_count'], 1)

    def test_missing_or_unterminated_page_is_not_guessed(self):
        self.assertIsNone(audit_car_page(b'ESP32-C3 Car'))
        self.assertIsNone(audit_car_page(b'<html>not the car page</html>'))


if __name__ == '__main__':
    unittest.main()
