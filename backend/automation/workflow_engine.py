import os
import json
import threading
from typing import Dict
from backend.utils.logger import logger
from backend.automation.workflow_templates import DEFAULT_TEMPLATES
from backend.automation.task_executor import execute_task

class WorkflowEngine:
    def __init__(self, config_path: str = None):
        if config_path is None:
            self.config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.config_path = os.path.join(self.config_dir, "config", "user_workflows.json")
        else:
            self.config_path = config_path
            
        self.user_workflows = {}
        self.load_user_workflows()

    def load_user_workflows(self):
        """Loads user-defined workflows from file."""
        if not os.path.exists(self.config_path):
            logger.info(f"User workflows file not found. Creating default at {self.config_path}")
            self.user_workflows = {}
            self.save_user_workflows()
            return
            
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.user_workflows = json.load(f)
                logger.info("User workflows loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading user workflows: {e}")
            self.user_workflows = {}

    def save_user_workflows(self):
        """Saves user-defined workflows to configuration file."""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.user_workflows, f, indent=2)
            logger.info(f"User workflows saved successfully to {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save user workflows: {e}")
            return False

    def add_user_workflow(self, workflow_id: str, workflow_data: dict) -> bool:
        """Adds or updates a custom user-defined workflow."""
        self.user_workflows[workflow_id] = workflow_data
        return self.save_user_workflows()

    def get_workflow(self, workflow_id: str) -> dict:
        """Retrieves a workflow by its ID from user preferences or system templates."""
        if workflow_id in self.user_workflows:
            return self.user_workflows[workflow_id]
        return DEFAULT_TEMPLATES.get(workflow_id)

    def run_workflow_by_id(self, workflow_id: str) -> bool:
        """Runs a workflow by its ID asynchronously in a background thread."""
        wf = self.get_workflow(workflow_id)
        if not wf:
            logger.warning(f"Workflow '{workflow_id}' not found.")
            return False
            
        thread = threading.Thread(
            target=self.execute_workflow,
            args=(wf,),
            daemon=True
        )
        thread.start()
        return True

    def execute_workflow(self, workflow: dict):
        """Synchronously executes the given workflow dictionary."""
        name = workflow.get("name", "Unnamed Workflow")
        logger.info(f"Starting execution of workflow: '{name}'")
        
        steps = workflow.get("steps", [])
        total_steps = len(steps)
        self.notify_status(name, "running", 0, total_steps)
        
        success = True
        execution_type = workflow.get("execution", "sequential")
        
        try:
            if execution_type == "parallel":
                success = self._execute_steps_parallel(steps)
            else:
                success = self._execute_steps_sequential(steps, name, total_steps)
        except Exception as e:
            logger.error(f"Failed to run workflow '{name}': {e}")
            success = False
            
        status = "completed" if success else "failed"
        self.notify_status(name, status, total_steps if success else 0, total_steps)
        logger.info(f"Workflow '{name}' execution status: {status.upper()}")

    def _execute_steps_sequential(self, steps: list, name: str, total_steps: int) -> bool:
        """Executes a list of steps sequentially (one by one)."""
        for index, step in enumerate(steps):
            self.notify_status(name, "running", index + 1, total_steps)
            if "steps" in step:
                nested_success = self._execute_nested_block(step)
                if not nested_success:
                    return False
            else:
                success = execute_task(step)
                if not success:
                    return False
        return True

    def _execute_steps_parallel(self, steps: list) -> bool:
        """Executes a list of steps in parallel (concurrently)."""
        threads = []
        results = [False] * len(steps)
        
        def run_step_thread(idx, step_dict):
            try:
                if "steps" in step_dict:
                    results[idx] = self._execute_nested_block(step_dict)
                else:
                    results[idx] = execute_task(step_dict)
            except Exception as e:
                logger.error(f"Error in parallel thread task: {e}")
                results[idx] = False

        for index, step in enumerate(steps):
            t = threading.Thread(
                target=run_step_thread,
                args=(index, step),
                daemon=True
            )
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        return all(results)

    def _execute_nested_block(self, block: dict) -> bool:
        """Helper to run a nested sequential or parallel steps block."""
        nested_steps = block.get("steps", [])
        exec_type = block.get("execution", "sequential").lower()
        if exec_type == "parallel":
            return self._execute_steps_parallel(nested_steps)
        else:
            for step in nested_steps:
                if "steps" in step:
                    if not self._execute_nested_block(step):
                        return False
                else:
                    if not execute_task(step):
                        return False
            return True

    def notify_status(self, name: str, status: str, step_index: int, total_steps: int):
        """Sends status update message to Connected WebSocket HUD Client."""
        try:
            from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType
            from backend.websocket.socket_manager import manager
            
            event = JarvisEvent(JarvisEventType.SYSTEM_UPDATE, {
                "workflow_update": {
                    "name": name,
                    "status": status.upper(),
                    "step": step_index,
                    "total": total_steps
                }
            })
            dispatcher.emit_sync(event, loop=manager.loop)
        except Exception:
            pass

# Shared singleton instance
workflow_engine = WorkflowEngine()
