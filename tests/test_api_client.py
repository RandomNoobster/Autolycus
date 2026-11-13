"""
Unit tests for api_client module

Tests the synchronous GraphQL query function used for Flask API routes.
"""
import os
import unittest
from unittest.mock import Mock, patch

import requests

from logic import api_client


class TestApiClientSync(unittest.TestCase):
    """Test synchronous API client functions."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.api_key = "test_api_key_12345"
        self.test_query = """
        query {
          alliances(first: 10) {
            data {
              id
              name
              acronym
            }
          }
        }
        """
    
    @patch('logic.api_client.requests.post')
    def test_query_sync_success(self, mock_post):
        """Test successful synchronous GraphQL query."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            'data': {
                'alliances': {
                    'data': [
                        {'id': '1', 'name': 'Test Alliance', 'acronym': 'TEST'},
                        {'id': '2', 'name': 'Another Alliance', 'acronym': 'ANOT'},
                    ]
                }
            }
        }
        mock_post.return_value = mock_response
        
        result = api_client.query_sync(self.test_query, self.api_key)
        
        self.assertIn('data', result)
        self.assertIn('alliances', result['data'])
        self.assertEqual(len(result['data']['alliances']['data']), 2)
    
    @patch('logic.api_client.requests.post')
    def test_query_sync_with_variables(self, mock_post):
        """Test synchronous query with variables."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {'data': {}}
        mock_post.return_value = mock_response
        
        variables = {"name": "test"}
        api_client.query_sync(self.test_query, self.api_key, variables)
        
        # Verify variables were passed in payload
        call_args = mock_post.call_args
        payload = call_args[1]['json']
        self.assertIn('variables', payload)
        self.assertEqual(payload['variables'], variables)
    
    @patch('logic.api_client.requests.post')
    def test_query_sync_invalid_api_key(self, mock_post):
        """Test handling of invalid API key."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_response.json.return_value = {
            'error': {
                'errors': [{'message': 'Invalid api_key'}]
            }
        }
        mock_post.return_value = mock_response
        
        with self.assertRaises(ConnectionError) as context:
            api_client.query_sync(self.test_query, self.api_key)
        
        self.assertIn('Invalid API key', str(context.exception))
    
    @patch('logic.api_client.requests.post')
    @patch('time.sleep')
    def test_query_sync_rate_limiting(self, mock_sleep, mock_post):
        """Test rate limit handling."""
        # First response hits rate limit
        mock_response_limited = Mock()
        mock_response_limited.status_code = 429
        mock_response_limited.headers = {
            'X-Ratelimit-Remaining': '0',
            'X-Ratelimit-Reset-After': '2'
        }
        mock_response_limited.json.return_value = {}
        
        # Second response succeeds
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.headers = {}
        mock_response_success.json.return_value = {'data': {}}
        
        mock_post.side_effect = [mock_response_limited, mock_response_success]
        
        result = api_client.query_sync(self.test_query, self.api_key)
        
        # Verify sleep was called with the reset time
        mock_sleep.assert_called_once_with(2)
        self.assertIn('data', result)
    
    @patch('logic.api_client.requests.post')
    def test_query_sync_json_decode_error(self, mock_post):
        """Test handling of invalid JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError(
            "Expecting value", "", 0
        )
        mock_response.text = "Invalid JSON response"
        mock_post.return_value = mock_response
        
        with self.assertRaises(Exception) as context:
            api_client.query_sync(self.test_query, self.api_key)
        
        self.assertIn('Invalid JSON response', str(context.exception))
    
    @patch('logic.api_client.requests.post')
    @patch('time.sleep')
    def test_query_sync_retry_logic(self, mock_sleep, mock_post):
        """Test retry logic on temporary failures."""
        # First two calls fail, third succeeds
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.headers = {}
        mock_response_fail.json.return_value = {'errors': ['Server error']}
        
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.headers = {}
        mock_response_success.json.return_value = {'data': {}}
        
        mock_post.side_effect = [
            mock_response_fail,
            mock_response_fail,
            mock_response_success
        ]
        
        result = api_client.query_sync(self.test_query, self.api_key)
        
        # Verify retries occurred (2 sleeps for 2 retries)
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertIn('data', result)

    def tearDown(self):
        # Responses that use up the rate-limit window hold back the next request
        # process-wide; don't let one test's window leak into the next.
        api_client._rate_limited_until = 0.0

    @patch('logic.api_client.requests.post')
    def test_query_sync_ignores_error_text_inside_player_data(self, mock_post):
        """Player-written text such as a nation name is data, not a server error."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            'data': {'nations': {'data': [{'nation_name': 'Internal Server Error'}]}}
        }
        mock_post.return_value = mock_response

        result = api_client.query_sync(self.test_query, self.api_key)

        self.assertEqual(result['data']['nations']['data'][0]['nation_name'], 'Internal Server Error')

    @patch('logic.api_client.requests.post')
    @patch('time.sleep')
    def test_query_sync_keeps_the_reply_that_used_up_the_window(self, mock_sleep, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'X-Ratelimit-Remaining': '0', 'X-Ratelimit-Reset-After': '30'}
        mock_response.json.return_value = {'data': {'ok': True}}
        mock_post.return_value = mock_response

        result = api_client.query_sync(self.test_query, self.api_key)

        self.assertEqual(result, {'data': {'ok': True}})
        self.assertEqual(mock_post.call_count, 1)
        mock_sleep.assert_not_called()

    @patch('logic.api_client.requests.post')
    @patch('time.sleep')
    def test_query_sync_gives_up_when_rate_limiting_persists(self, mock_sleep, mock_post):
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {'Retry-After': '1'}
        mock_response.json.return_value = {}
        mock_post.return_value = mock_response

        with self.assertRaises(api_client.PnWServerError):
            api_client.query_sync(self.test_query, self.api_key)

        self.assertEqual(mock_sleep.call_count, api_client.MAX_RATE_LIMIT_WAITS)

    @patch('logic.api_client.requests.post')
    def test_query_sync_keeps_the_api_key_out_of_connection_errors(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError(
            f"Max retries exceeded with url: /graphql?api_key={self.api_key}"
        )

        with self.assertRaises(ConnectionError) as context:
            api_client.query_sync(self.test_query, self.api_key)

        self.assertNotIn(self.api_key, str(context.exception))
        # The original exception (which repeats the URL) is not chained into tracebacks.
        self.assertTrue(context.exception.__suppress_context__)


class TestServerErrorDetection(unittest.TestCase):
    def test_only_the_error_envelope_signals_a_server_error(self):
        detect = api_client._is_pnw_server_error_response
        self.assertTrue(detect(500, {}))
        self.assertTrue(detect(200, {'errors': [{'message': 'Internal server error'}], 'data': None}))
        self.assertFalse(detect(200, {'data': {'nations': {'data': [{'discord': 'internal server error'}]}}}))

    def test_invalid_key_detection_handles_both_error_shapes(self):
        detect = api_client._is_invalid_api_key_response
        self.assertTrue(detect({'error': {'errors': [{'message': 'Invalid api_key'}]}}))
        self.assertTrue(detect({'error': 'invalid api_key'}))
        self.assertFalse(detect({'data': {}}))


if __name__ == '__main__':
    unittest.main()
