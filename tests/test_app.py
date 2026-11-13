import unittest

from app import app


class MessengerBotTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_root_returns_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('MessengerBo', response.get_data(as_text=True))

    def test_health_route(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertIn('ok', response.get_json()['status'])

    def test_webhook_verification(self):
        response = self.client.get('/webhook?hub.mode=subscribe&hub.verify_token=demo_verify_token&hub.challenge=challenge123')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), 'challenge123')

    def test_local_message_echo(self):
        response = self.client.post('/message', json={'text': 'hello'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['reply'], 'Echo: hello')


if __name__ == '__main__':
    unittest.main()
