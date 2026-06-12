import os
import requests
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
                answer = brain.ask_gemini(prompt)
                
                # Check if the returned answer is an error indicator string
                if (answer and 
                    not answer.startswith("My AI brain returned an error") and 
                    not answer.startswith("Sorry, I couldn't reach my AI brain")):
                    logger.info(f"Success: Prompt resolved via Gemini model '{brain.GEMINI_MODEL}'")
                    return answer
                else:
                    logger.warning(f"Gemini API returned error state: '{answer}'. Initiating Ollama fallback.")
            else:
                logger.warning("Gemini API key is not configured. Routing directly to local Ollama.")
        except Exception as e:
            logger.error(f"Gemini generation raised an exception: {e}. Initiating Ollama fallback.")

        # 2. Fallback to local Ollama
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
        # Convert history format from brain.chat_history:
        # turn = {"role": "user"/"model", "text": ...}
        # Ollama expects: {"role": "user"/"assistant", "content": ...}
        messages = [{"role": "system", "content": self.system_prompt}]
        
        for turn in brain.chat_history[-brain.MAX_HISTORY:]:
            role = "user" if turn["role"] == "user" else "assistant"
            messages.append({"role": role, "content": turn["text"]})
            
        messages.append({"role": "user", "content": prompt})
        
        url = f"{self.ollama_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 256
            }
        }
        
        r = requests.post(url, json=payload, timeout=25)
        if r.status_code != 200:
            raise RuntimeError(f"Ollama returned HTTP error code {r.status_code}: {r.text[:100]}")
            
        res_json = r.json()
        answer = res_json["message"]["content"].strip()
        
        # Synchronize fallback response back to the shared chat memory
        brain.chat_history.append({"role": "user", "text": prompt})
        brain.chat_history.append({"role": "model", "text": answer})
        
        return answer

# Global Router Singleton
router = LLMRouter()
