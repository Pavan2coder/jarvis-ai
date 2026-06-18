from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional, Union
import requests
from backend.utils.logger import logger
from backend.core import config
from network.retry_manager import RetryManager, RetryConfig, APIException

class APIClient:
    """Core HTTP client encapsulating requests, timeouts, and RetryManager."""
    
    def __init__(
        self,
        default_timeout: Tuple[float, float] = (5.0, 20.0),
        default_retry_config: Optional[RetryConfig] = None
    ):
        """Initializes APIClient.
        
        Args:
            default_timeout: Tuple indicating (connect_timeout, read_timeout) in seconds.
            default_retry_config: Optional default retry configuration.
        """
        self.default_timeout = default_timeout
        self.default_retry_config = default_retry_config or RetryConfig()

    def request(
        self,
        method: str,
        url: str,
        timeout: Optional[Union[float, Tuple[float, float]]] = None,
        retry_config: Optional[RetryConfig] = None,
        **kwargs: Any
    ) -> requests.Response:
        """Sends an HTTP request with automatic retry logic and exception mapping.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            timeout: Custom timeout overriding the client default
            retry_config: Custom retry configuration overriding the client default
            **kwargs: Extra parameters passed to requests.request (headers, json, params, etc.)
            
        Returns:
            The successful requests.Response object.
            
        Raises:
            APIException subclasses depending on the error classification.
        """
        req_timeout = timeout if timeout is not None else self.default_timeout
        req_retry = retry_config or self.default_retry_config

        def _execute_request() -> requests.Response:
            response = requests.request(method, url, timeout=req_timeout, **kwargs)
            response.raise_for_status()
            return response

        return RetryManager.execute(_execute_request, retry_config=req_retry)


# ==========================================
# LLM Provider Abstractions
# ==========================================

class LLMProvider(ABC):
    """Abstract base class representing an LLM backend provider."""
    
    @abstractmethod
    def generate(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        system_instruction: Optional[str] = None
    ) -> str:
        """Generates a text completion response.
        
        Args:
            prompt: The current user message/prompt.
            history: Optional conversation history in normalized format:
                     [{"role": "user"|"model"|"assistant", "text": "message_content"}]
            system_instruction: System prompt to govern assistant personality.
            
        Returns:
            Spoken text answer as a string.
        """
        pass

    @abstractmethod
    def verify(self) -> Tuple[bool, str]:
        """Probes the provider endpoint to verify authorization and status.
        
        Returns:
            A tuple (success_boolean, status_message).
        """
        pass


# ==========================================
# Gemini Provider Implementation
# ==========================================

class GeminiProvider(LLMProvider):
    """Concrete LLMProvider utilizing Google Gemini REST API endpoints."""
    
    def __init__(self, api_key: str, model_name: str, client: Optional[APIClient] = None):
        self.api_key = api_key
        self.model_name = model_name
        self.client = client or APIClient()

    def generate(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        system_instruction: Optional[str] = None
    ) -> str:
        if not self.api_key:
            raise APIException("Gemini API key is not configured.")

        # Format history and current prompt according to Gemini specification
        contents = []
        if history:
            for turn in history:
                # Gemini roles are strictly 'user' or 'model'
                role = "user" if turn.get("role") == "user" else "model"
                contents.append({"role": role, "parts": [{"text": turn.get("text", "")}]})
        
        # Add the current turn
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 256},
        }

        if system_instruction:
            body["system_instruction"] = {"parts": [{"text": system_instruction}]}

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent?key={self.api_key}"
        )

        try:
            # We enforce a slightly shorter timeout for conversational responses to prevent lockups
            response = self.client.request("POST", url, json=body, timeout=(5.0, 20.0))
            data = response.json()
            
            # Extract generated response text
            candidates = data.get("candidates")
            if not candidates or not candidates[0].get("content"):
                logger.error(f"Gemini API returned unexpected structure: {data}")
                raise APIException("Unexpected response format from Gemini API.")
                
            text = candidates[0]["content"]["parts"][0]["text"].strip()
            return text
        except APIException as e:
            logger.error(f"Gemini generation API error: {e}")
            raise e
        except Exception as e:
            logger.error(f"Failed to process Gemini response: {e}")
            raise APIException("Failed to process Gemini response.", e)

    def verify(self) -> Tuple[bool, str]:
        """Verify model connectivity and authorization with a minimal probe."""
        if not self.api_key:
            return False, "No Gemini API key set."
            
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent?key={self.api_key}"
        )
        probe_body = {
            "contents": [{"parts": [{"text": "hi"}]}],
            "generationConfig": {"maxOutputTokens": 5}
        }
        
        try:
            # Short timeout and only 1 retry for model verification
            cfg = RetryConfig(max_retries=1, initial_backoff=0.5, max_backoff=1.0)
            self.client.request("POST", url, json=probe_body, timeout=(3.0, 5.0), retry_config=cfg)
            return True, f"Gemini online — using model '{self.model_name}'."
        except APIException as e:
            return False, str(e)


# ==========================================
# Ollama Provider Implementation
# ==========================================

class OllamaProvider(LLMProvider):
    """Concrete LLMProvider utilizing local Ollama instances."""
    
    def __init__(self, ollama_url: str, model_name: str, client: Optional[APIClient] = None):
        self.ollama_url = ollama_url.rstrip('/')
        self.model_name = model_name
        self.client = client or APIClient()

    def generate(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        system_instruction: Optional[str] = None
    ) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
            
        if history:
            for turn in history:
                # Ollama uses 'user' and 'assistant' roles
                role = "user" if turn.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": turn.get("text", "")})
                
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 256
            }
        }

        url = f"{self.ollama_url}/api/chat"

        try:
            # Slightly longer read timeout for local inference
            response = self.client.request("POST", url, json=payload, timeout=(3.0, 25.0))
            res_json = response.json()
            answer = res_json["message"]["content"].strip()
            return answer
        except APIException as e:
            logger.error(f"Ollama generation API error: {e}")
            raise e
        except Exception as e:
            logger.error(f"Failed to process Ollama response: {e}")
            raise APIException("Failed to process Ollama response.", e)

    def verify(self) -> Tuple[bool, str]:
        """Probe the local Ollama instance for readiness."""
        url = f"{self.ollama_url}/api/tags"
        try:
            # Fast verification check
            cfg = RetryConfig(max_retries=1, initial_backoff=0.5, max_backoff=1.0)
            response = self.client.request("GET", url, timeout=(2.0, 3.0), retry_config=cfg)
            models = [m["name"] for m in response.json().get("models", [])]
            
            # Check if the requested model is actually available
            if self.model_name in models or any(self.model_name in m for m in models):
                return True, f"Ollama online — using model '{self.model_name}'."
            else:
                return False, f"Ollama online, but model '{self.model_name}' is not downloaded (available: {models})."
        except APIException as e:
            return False, f"Ollama unreachable: {str(e)}"


# ==========================================
# LLM Provider Registry
# ==========================================

class LLMClientRegistry:
    """Registry managing LLM provider lifecycles and registration."""
    
    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._default_provider: Optional[str] = None

    def register(self, name: str, provider: LLMProvider, is_default: bool = False) -> None:
        self._providers[name] = provider
        if is_default or self._default_provider is None:
            self._default_provider = name

    def get(self, name: str) -> LLMProvider:
        if name not in self._providers:
            raise KeyError(f"LLM Provider '{name}' is not registered.")
        return self._providers[name]

    def get_default(self) -> LLMProvider:
        if not self._default_provider:
            raise RuntimeError("No default LLM Provider registered in LLMClientRegistry.")
        return self.get(self._default_provider)

    def list_providers(self) -> List[str]:
        return list(self._providers.keys())


# Singleton instance of registry initialized with configured clients
registry = LLMClientRegistry()

def initialize_registry():
    """Helper function to load registry clients with current config settings."""
    gemini_key = getattr(config, "GEMINI_API_KEY", "")
    gemini_model = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
    ollama_url = getattr(config, "OLLAMA_URL", "http://localhost:11434")
    ollama_model = getattr(config, "OLLAMA_MODEL", "llama3")
    
    registry.register(
        "gemini", 
        GeminiProvider(api_key=gemini_key, model_name=gemini_model),
        is_default=True
    )
    
    registry.register(
        "ollama",
        OllamaProvider(ollama_url=ollama_url, model_name=ollama_model),
        is_default=False
    )

# Automatically initialize registry
initialize_registry()
