import os
from backend.core import config
from backend.utils.logger import logger
from backend.assistant import brain

class LLMRouter:
    def __init__(self):
        self.ollama_url = config.OLLAMA_URL
        self.ollama_model = config.OLLAMA_MODEL
        self.system_prompt = config.SYSTEM_PROMPT

    def ask_llm(self, prompt: str) -> str:
        """Centralized router that attempts to answer with local personality rules,
        Google Gemini, and falls back to a local Ollama instance upon failures.
        """
        logger.info(f"Routing prompt: '{prompt[:40]}...'")
        
        # 1. Check local personality rules first
        try:
            from backend.assistant.personality import check_personality_rules
            local_ans = check_personality_rules(prompt)
            if local_ans:
                logger.info("Success: Prompt resolved locally via Personality Engine.")
                return local_ans
        except Exception as e:
            logger.error(f"Error in local personality check: {e}")
            
        # 2. Attempt to resolve via Gemini
        try:
            if brain.gemini_ready():
                logger.info(f"Attempting to query Gemini API using model '{brain.GEMINI_MODEL}'...")
                from network.api_client import registry, GeminiProvider
                
                gemini_provider = registry.get("gemini")
                if isinstance(gemini_provider, GeminiProvider):
                    # Keep model in sync with the dynamically verified brain model
                    gemini_provider.model_name = brain.GEMINI_MODEL
                
                # Fetch recent conversation memory
                history_list = list(brain.chat_history[-brain.MAX_HISTORY:])
                answer = gemini_provider.generate(
                    prompt=prompt,
                    history=history_list,
                    system_instruction=self.system_prompt
                )
                
                # Synchronize back to the shared chat memory
                brain.chat_history.append({"role": "user", "text": prompt})
                brain.chat_history.append({"role": "model", "text": answer})
                
                logger.info(f"Success: Prompt resolved via Gemini model '{brain.GEMINI_MODEL}'")
                return answer
            else:
                logger.warning("Gemini API key is not configured. Routing directly to local Ollama.")
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}. Initiating Ollama fallback.")

        # 3. Fallback to local Ollama
        logger.info(f"Attempting fallback query to local Ollama using model '{self.ollama_model}'...")
        try:
            answer = self._ask_ollama(prompt)
            logger.info(f"Success: Prompt resolved via Ollama model '{self.ollama_model}'")
            return answer
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            return "Both my Gemini brain and local Ollama backup failed to resolve your request."

    def _ask_ollama(self, prompt: str) -> str:
        """Queries local Ollama chat API mapping the existing chat history."""
        from network.api_client import registry, OllamaProvider
        
        ollama_provider = registry.get("ollama")
        if isinstance(ollama_provider, OllamaProvider):
            ollama_provider.ollama_url = self.ollama_url
            ollama_provider.model_name = self.ollama_model
            
        history_list = list(brain.chat_history[-brain.MAX_HISTORY:])
        answer = ollama_provider.generate(
            prompt=prompt,
            history=history_list,
            system_instruction=self.system_prompt
        )
        
        # Synchronize fallback response back to the shared chat memory
        brain.chat_history.append({"role": "user", "text": prompt})
        brain.chat_history.append({"role": "model", "text": answer})
        
        return answer

# Global Router Singleton
router = LLMRouter()

