import asyncio
import traceback # For detailed error logging
from datetime import datetime, timezone # To set UTC timestamps
import sys
import os

# Add the project root to the Python path to allow for absolute imports of browser_use
# This assumes agent_executor.py is in /app/test_automation_api and browser_use is in /app/browser_use
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now try to import from browser_use and local models
try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from .models import TestRun # Assuming models.py is in the same directory (test_automation_api)
    
    # Imports from the browser_use library
    from browser_use.agent.service import Agent
    from browser_use.browser.session import BrowserSession, BrowserProfile
    from browser_use.agent.views import AgentHistoryList
except ImportError as e:
    print(f"PYTHONPATH: {sys.path}")
    print(f"Current working dir: {os.getcwd()}")
    # This print helps in diagnosing if imports fail during runtime
    print(f"Error during initial imports in agent_executor.py: {e}") 
    raise


class BrowserAgentExecutor:
    def __init__(self, llm: BaseChatModel):
        if llm is None:
            # As per subtask requirement, raise ValueError if llm is None.
            raise ValueError("LLM instance cannot be None for BrowserAgentExecutor.")
        self.llm = llm
        # Potentially initialize a default BrowserProfile here if needed
        # self.default_browser_profile = BrowserProfile(headless=True) # Example

    async def execute_scenario(self, scenario_definition: str, test_run: TestRun, test_runs_db: list[TestRun]):
        print(f"Starting agent execution for TestRun ID: {test_run.id} with Scenario ID: {test_run.scenarioId}")
        
        # Find the test_run in the db to update it directly
        current_run_in_db = next((r for r in test_runs_db if r.id == test_run.id), None)
        if not current_run_in_db:
            print(f"Error: TestRun ID {test_run.id} not found in db for updates. Will update passed TestRun object directly.")
            current_run_in_db = test_run 

        # self.llm is guaranteed to not be None here due to constructor check.
        # No need for:
        # if self.llm is None:
        #     print(f"Error: LLM not initialized. Cannot execute scenario for TestRun ID: {test_run.id}")
        #     ...
        #     return

        try:
            # 1. Create a BrowserSession
            browser_profile = BrowserProfile(
                headless=True, 
                # Example: Configure downloads if your agent might download files
                # save_downloads_path=os.path.join(project_root, "downloads", test_run.id), 
                # Ensure the path is absolute and unique per run if needed
                # Example: Restrict domains for security
                # allowed_domains=["example.com"] 
            )
            # Ensure download path exists if configured
            # if browser_profile.save_downloads_path:
            #    os.makedirs(browser_profile.save_downloads_path, exist_ok=True)

            async with BrowserSession(browser_profile=browser_profile) as browser_session:
                # 2. Instantiate the Agent
                agent = Agent(
                    task=scenario_definition, # This is the prompt or task for the agent
                    llm=self.llm,
                    browser_session=browser_session,
                    # Add other agent parameters if necessary:
                    # use_vision=True, # If the model supports vision and it's needed
                    # generate_gif=False, # Control GIF generation
                    # verbose=True, # For more detailed agent logging
                )

                # 3. Run the agent
                print(f"Agent for TestRun ID: {test_run.id} starting agent.run()...")
                # The run method is async
                history: AgentHistoryList = await agent.run(max_steps=20) # Set a reasonable max_steps
                print(f"Agent for TestRun ID: {test_run.id} finished agent.run().")

                # 4. Update TestRun object with results
                current_run_in_db.status = "Completed" if history.is_successful() else "Failed"
                current_run_in_db.logs.append(f"Agent execution finished. Final status: {current_run_in_db.status}")
                
                if history.errors():
                    for error_log in history.errors():
                        # Ensure error_log is a string or has a string representation
                        current_run_in_db.logs.append(f"Agent Error: {str(error_log)}")
                
                final_result_summary = history.final_result()
                if final_result_summary:
                    current_run_in_db.resultsSummary = str(final_result_summary)[:500] # Truncate

                # Example of storing structured output (e.g., last non-error message or specific extracted content)
                if history.history:
                    # Log all messages or just the final ones for brevity in example
                    for hist_item in history.history:
                        # Adapt based on actual structure of hist_item
                        log_message = f"Agent Log: Type={getattr(hist_item, 'type', 'N/A')}"
                        if hasattr(hist_item, 'message') and hist_item.message:
                            log_message += f", Message='{str(hist_item.message)[:100]}...'" # Truncate long messages
                        if hasattr(hist_item, 'result') and hist_item.result:
                             # Assuming result might be complex, take string summary
                            log_message += f", Result='{str(hist_item.result)[:100]}...'"
                        current_run_in_db.logs.append(log_message)
                    
                    # Example for output field based on final history item:
                    # last_item = history.history[-1]
                    # if hasattr(last_item, 'result') and last_item.result and isinstance(last_item.result, list) and len(last_item.result) > 0:
                    #    # Assuming result is a list and we take the first element
                    #    action_result = last_item.result[0]
                    #    current_run_in_db.output = {
                    #        "last_thought": getattr(action_result, 'thought', None),
                    #        "last_action": getattr(action_result, 'action', None),
                    #        "extracted_content": getattr(action_result, 'extracted_content', None)
                    #    }


        except Exception as e:
            print(f"Error during agent execution for TestRun ID: {test_run.id}: {e}")
            detailed_error = traceback.format_exc()
            current_run_in_db.status = "Failed"
            current_run_in_db.logs.append(f"Agent execution critical error: {e}")
            current_run_in_db.logs.append(f"Traceback: {detailed_error}")
            current_run_in_db.resultsSummary = f"Execution error: {str(e)[:200]}" # Truncate error
        finally:
            current_run_in_db.endTime = datetime.now(timezone.utc)
            print(f"Finished processing and updating TestRun ID: {test_run.id}. Final status: {current_run_in_db.status}")

# Example Usage (conceptual)
# (Same as before, removed for brevity in overwrite_file_with_block)
# if __name__ == "__main__":
#     print("BrowserAgentExecutor defined. For usage, integrate with the FastAPI app.")
