import unittest
from unittest.mock import Mock, patch
import requests
from network.retry_manager import (
    RetryConfig, RetryManager, categorize_exception,
    APIException, TransientAPIError, FatalAPIError, AuthAPIError,
    QuotaAPIError, TimeoutAPIError, ConnectionAPIError
)
from network.api_client import (
    APIClient, LLMClientRegistry, GeminiProvider, OllamaProvider
)

class TestRetryManager(unittest.TestCase):

    def test_backoff_calculation_no_jitter(self):
        config = RetryConfig(
            max_retries=3,
            initial_backoff=1.0,
            max_backoff=10.0,
            backoff_factor=2.0,
            jitter=False
        )
        # 1.0 * (2.0 ** 0) = 1.0
        self.assertEqual(RetryManager.calculate_backoff(0, config), 1.0)
        # 1.0 * (2.0 ** 1) = 2.0
        self.assertEqual(RetryManager.calculate_backoff(1, config), 2.0)
        # 1.0 * (2.0 ** 2) = 4.0
        self.assertEqual(RetryManager.calculate_backoff(2, config), 4.0)
        # Cap at max_backoff (10.0)
        # 1.0 * (2.0 ** 4) = 16.0 -> capped at 10.0
        self.assertEqual(RetryManager.calculate_backoff(4, config), 10.0)

    def test_backoff_calculation_with_jitter(self):
        config = RetryConfig(
            max_retries=3,
            initial_backoff=1.0,
            max_backoff=10.0,
            backoff_factor=2.0,
            jitter=True
        )
        for attempt in range(5):
            backoff = RetryManager.calculate_backoff(attempt, config)
            # Should be >= 0.0
            self.assertGreaterEqual(backoff, 0.0)
            # Should be <= min(max_backoff, initial_backoff * (backoff_factor ** attempt))
            temp = config.initial_backoff * (config.backoff_factor ** attempt)
            expected_max = min(config.max_backoff, temp)
            self.assertLessEqual(backoff, expected_max)

    def test_categorize_exception_http_codes(self):
        # Helper to mock HTTPError
        def make_http_error(status_code, response_text=""):
            response = Mock()
            response.status_code = status_code
            response.text = response_text
            exc = requests.exceptions.HTTPError()
            exc.response = response
            return exc

        # 401/403 -> AuthAPIError
        self.assertIsInstance(categorize_exception(make_http_error(401)), AuthAPIError)
        self.assertIsInstance(categorize_exception(make_http_error(403)), AuthAPIError)

        # 429 Hard Quota vs Soft Rate Limit
        quota_err = categorize_exception(make_http_error(429, "quota exhausted"))
        self.assertIsInstance(quota_err, QuotaAPIError)
        self.assertTrue(quota_err.is_hard_limit)

        rate_err = categorize_exception(make_http_error(429, "Rate limit exceeded. Try again later."))
        self.assertIsInstance(rate_err, QuotaAPIError)
        self.assertFalse(rate_err.is_hard_limit)

        # 5xx -> TransientAPIError
        self.assertIsInstance(categorize_exception(make_http_error(500)), TransientAPIError)
        self.assertIsInstance(categorize_exception(make_http_error(503)), TransientAPIError)

        # Other 4xx -> FatalAPIError
        self.assertIsInstance(categorize_exception(make_http_error(400)), FatalAPIError)
        self.assertIsInstance(categorize_exception(make_http_error(404)), FatalAPIError)

    def test_categorize_exception_network_errors(self):
        # Timeouts
        timeout_exc = requests.exceptions.Timeout("Read timeout")
        self.assertIsInstance(categorize_exception(timeout_exc), TimeoutAPIError)

        # Connection drop
        conn_exc = requests.exceptions.ConnectionError("Connection refused")
        self.assertIsInstance(categorize_exception(conn_exc), ConnectionAPIError)

    @patch('time.sleep', return_value=None)
    def test_execute_with_retries_success(self, mock_sleep):
        # Succeeded first time
        mock_func = Mock(return_value="success")
        result = RetryManager.execute(mock_func)
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 1)

    @patch('time.sleep', return_value=None)
    def test_execute_with_retries_transient_recovery(self, mock_sleep):
        # Fails once with retriable error, then succeeds
        side_effects = [
            requests.exceptions.Timeout("Timeout"),
            "recovered"
        ]
        mock_func = Mock(side_effect=side_effects)
        config = RetryConfig(max_retries=2, initial_backoff=0.1, jitter=False)
        
        result = RetryManager.execute(mock_func, retry_config=config)
        self.assertEqual(result, "recovered")
        self.assertEqual(mock_func.call_count, 2)
        mock_sleep.assert_called_once()

    @patch('time.sleep', return_value=None)
    def test_execute_with_retries_max_reached(self, mock_sleep):
        # Fails every time with retriable error
        mock_func = Mock(side_effect=requests.exceptions.Timeout("Timeout"))
        config = RetryConfig(max_retries=3, initial_backoff=0.1, jitter=False)
        
        with self.assertRaises(TimeoutAPIError):
            RetryManager.execute(mock_func, retry_config=config)
            
        self.assertEqual(mock_func.call_count, 4)  # 1 initial call + 3 retries
        self.assertEqual(mock_sleep.call_count, 3)

    @patch('time.sleep', return_value=None)
    def test_execute_fails_fast_on_fatal(self, mock_sleep):
        # Fails immediately on Fatal error (e.g. 401 Auth error)
        response = Mock()
        response.status_code = 401
        response.text = "Unauthorized"
        http_error = requests.exceptions.HTTPError(response=response)
        
        mock_func = Mock(side_effect=http_error)
        config = RetryConfig(max_retries=3)
        
        with self.assertRaises(AuthAPIError):
            RetryManager.execute(mock_func, retry_config=config)
            
        self.assertEqual(mock_func.call_count, 1)  # No retries
        mock_sleep.assert_not_called()


class TestAPIClient(unittest.TestCase):

    @patch('requests.request')
    def test_api_client_request_success(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_request.return_value = mock_response
        
        client = APIClient()
        response = client.request("GET", "https://api.example.com/test")
        
        self.assertEqual(response, mock_response)
        mock_request.assert_called_once_with(
            "GET", "https://api.example.com/test", timeout=(5.0, 20.0)
        )

    @patch('time.sleep', return_value=None)
    @patch('requests.request')
    def test_api_client_request_retry_on_503(self, mock_request, mock_sleep):
        # First call: 503, Second call: 200
        response_503 = Mock()
        response_503.status_code = 503
        response_503.text = "Service Unavailable"
        response_503.raise_for_status.side_effect = requests.exceptions.HTTPError(response=response_503)
        
        response_200 = Mock()
        response_200.status_code = 200
        response_200.raise_for_status.return_value = None
        
        mock_request.side_effect = [response_503, response_200]
        
        client = APIClient()
        config = RetryConfig(max_retries=2, initial_backoff=0.1, jitter=False)
        response = client.request("GET", "https://api.example.com/test", retry_config=config)
        
        self.assertEqual(response, response_200)
        self.assertEqual(mock_request.call_count, 2)


class TestProviders(unittest.TestCase):

    @patch('requests.request')
    def test_gemini_provider_generate_success(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Hello, I am Jarvis."}]
                }
            }]
        }
        mock_request.return_value = mock_response
        
        provider = GeminiProvider(api_key="fake_key", model_name="gemini-2.5-flash")
        result = provider.generate("hello", history=[{"role": "user", "text": "hi"}], system_instruction="Be polite")
        
        self.assertEqual(result, "Hello, I am Jarvis.")
        
        # Verify JSON body structure
        args, kwargs = mock_request.call_args
        json_body = kwargs["json"]
        self.assertEqual(json_body["system_instruction"]["parts"][0]["text"], "Be polite")
        self.assertEqual(len(json_body["contents"]), 2)
        self.assertEqual(json_body["contents"][0]["role"], "user")
        self.assertEqual(json_body["contents"][1]["role"], "user")

    @patch('requests.request')
    def test_ollama_provider_generate_success(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "content": "Local Ollama response."
            }
        }
        mock_request.return_value = mock_response
        
        provider = OllamaProvider(ollama_url="http://localhost:11434", model_name="llama3")
        result = provider.generate("hello", history=[{"role": "user", "text": "hi"}, {"role": "model", "text": "hey"}])
        
        self.assertEqual(result, "Local Ollama response.")
        
        # Verify message roles translation for Ollama ('assistant' instead of 'model')
        args, kwargs = mock_request.call_args
        json_body = kwargs["json"]
        messages = json_body["messages"]
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[2]["role"], "user")


if __name__ == '__main__':
    unittest.main()
