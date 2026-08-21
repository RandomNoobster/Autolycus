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


if __name__ == '__main__':
    unittest.main()
