import pytest
from fastapi.testclient import TestClient
from fastapi import BackgroundTasks # For type hinting if needed, though patching is key
import sys
import os
from datetime import datetime, timezone # Ensure timezone for endTime
from unittest.mock import patch, MagicMock, ANY
import asyncio # For potential sleeps, though direct execution is preferred for mocks

# Add the project root to the Python path to allow for absolute imports
# This assumes tests are in /app/test_automation_api/tests and main.py is in /app/test_automation_api
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now try to import the app
try:
    # Import 'app' and also the in-memory dbs for fixture and direct checks
    from test_automation_api.main import app, scenarios_db, test_runs_db, llm, agent_executor
    from test_automation_api.models import TestRun # For type checks
except ImportError as e:
    print(f"PYTHONPATH: {sys.path}")
    print(f"Current working dir: {os.getcwd()}")
    raise ImportError(f"Failed to import app or db instances: {e}. Check PYTHONPATH and file locations.")


client = TestClient(app)

# Shared dictionary to store IDs generated during tests
shared_ids = {}

# Fixture to clear databases before each test function
@pytest.fixture(autouse=True)
def clear_databases():
    scenarios_db.clear()
    test_runs_db.clear()
    shared_ids.clear()

# --- Test Scenario Endpoints ---

def test_create_scenario():
    response = client.post(
        "/api/scenarios",
        json={"name": "Login Test", "description": "Test login functionality", "scenarioDefinition": "{'steps': []}"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Login Test"
    assert "id" in data
    assert "createdAt" in data
    assert "updatedAt" in data
    shared_ids["scenario_id"] = data["id"]
    shared_ids["scenario_created_at"] = data["createdAt"]
    shared_ids["scenario_updated_at"] = data["updatedAt"]
    # Store scenario definition for later tests
    shared_ids["scenario_definition"] = data["scenarioDefinition"]


def test_get_scenarios():
    # First, create a scenario to ensure the list is not empty
    client.post("/api/scenarios", json={"name": "Initial Scenario", "description": "Desc", "scenarioDefinition": "{'steps': []}"})
    
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["name"] == "Initial Scenario"


def test_get_scenario_by_id():
    # Create a scenario first
    create_response = client.post(
        "/api/scenarios",
        json={"name": "Specific Scenario", "description": "To be fetched", "scenarioDefinition": "{'steps': ['action1']}"}
    )
    scenario_id = create_response.json()["id"]
    
    response = client.get(f"/api/scenarios/{scenario_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == scenario_id
    assert data["name"] == "Specific Scenario"


def test_get_scenario_not_found():
    response = client.get("/api/scenarios/non_existent_id")
    assert response.status_code == 404


def test_update_scenario():
    create_response = client.post(
        "/api/scenarios",
        json={"name": "Update Test", "description": "Before update", "scenarioDefinition": "{'steps': ['original_step']}"}
    )
    scenario_id = create_response.json()["id"]
    original_updated_at = create_response.json()["updatedAt"]

    # Ensure a small delay so updatedAt timestamp can change
    import time
    time.sleep(0.01)

    update_payload = {"description": "After update", "name": "Updated Name"}
    response = client.put(
        f"/api/scenarios/{scenario_id}",
        json=update_payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "After update"
    assert data["name"] == "Updated Name"
    assert data["id"] == scenario_id
    # Pydantic v2 datetime fields might include microseconds, direct string comparison can be tricky
    # We check if it's greater than original, assuming time moves forward
    assert datetime.fromisoformat(data["updatedAt"].replace("Z", "+00:00")) > datetime.fromisoformat(original_updated_at.replace("Z", "+00:00"))


def test_update_scenario_not_found():
    response = client.put(
        "/api/scenarios/non_existent_id",
        json={"description": "Trying to update non-existent"}
    )
    assert response.status_code == 404


def test_delete_scenario():
    create_response = client.post(
        "/api/scenarios",
        json={"name": "To Delete", "description": "This will be deleted", "scenarioDefinition": "{'type': 'delete_me'}"}
    )
    scenario_id = create_response.json()["id"]
    
    delete_response = client.delete(f"/api/scenarios/{scenario_id}")
    assert delete_response.status_code == 204
    
    get_response = client.get(f"/api/scenarios/{scenario_id}")
    assert get_response.status_code == 404


def test_delete_scenario_not_found():
    response = client.delete("/api/scenarios/non_existent_id")
    assert response.status_code == 404

# --- Test Run Endpoints ---

def setup_scenario_for_runs(): # Renamed from test_create_scenario to avoid pytest collection as a test
    # Ensure a scenario exists for run tests
    if "scenario_id" not in shared_ids or not any(s.id == shared_ids["scenario_id"] for s in scenarios_db):
        # If not in shared_ids or not in db (cleared by fixture), create it
        scenario_payload = {"name": "Scenario For Runs", 
                            "description": "Parent scenario for test runs", 
                            "scenarioDefinition": '{"type": "generic", "steps": ["step1"]}'}
        response = client.post("/api/scenarios", json=scenario_payload)
        assert response.status_code == 201
        data = response.json()
        shared_ids["scenario_id"] = data["id"]
        shared_ids["scenario_name"] = data["name"]
        shared_ids["scenario_definition"] = data["scenarioDefinition"] # Store definition
    return shared_ids["scenario_id"], shared_ids["scenario_name"], shared_ids["scenario_definition"]


@patch("test_automation_api.main.BackgroundTasks.add_task") # Patch where BackgroundTasks is used
@patch("test_automation_api.main.agent_executor.execute_scenario", new_callable=MagicMock)
def test_run_scenario_initiates_background_task(mock_execute_scenario: MagicMock, mock_add_task: MagicMock):
    scenario_id, scenario_name, scenario_def = setup_scenario_for_runs()
    
    run_inputs = {"param1": "value1"}
    response = client.post(
        f"/api/scenarios/{scenario_id}/run",
        json={"inputs": run_inputs}
    )
    
    assert response.status_code == 202
    data = response.json()
    assert data["scenarioId"] == scenario_id
    assert data["scenarioName"] == scenario_name
    assert data["status"] == "Running" # Initial status
    assert "id" in data
    run_id = data["id"]
    assert data["logs"] == ["Test run initiated via API."]
    assert data["inputs"] == run_inputs

    # Check that add_task was called correctly
    # The TestRun object (ANY) and test_runs_db (ANY) are dynamic
    mock_add_task.assert_called_once_with(
        mock_execute_scenario,  # This is the patched agent_executor.execute_scenario
        scenario_def,
        ANY, # The TestRun object created in the endpoint
        test_runs_db # The actual list instance from main
    )
    # Further check on the TestRun object passed to add_task
    args, _ = mock_add_task.call_args
    passed_test_run_arg = args[2] # The TestRun object
    assert isinstance(passed_test_run_arg, TestRun)
    assert passed_test_run_arg.id == run_id
    assert passed_test_run_arg.status == "Running"


@patch("test_automation_api.main.BackgroundTasks.add_task")
@patch("test_automation_api.main.agent_executor.execute_scenario", new_callable=MagicMock)
def test_run_scenario_no_inputs(mock_execute_scenario: MagicMock, mock_add_task: MagicMock):
    scenario_id, scenario_name, scenario_def = setup_scenario_for_runs()
    
    response = client.post(f"/api/scenarios/{scenario_id}/run") # No JSON body, run_create_data will be None
    
    assert response.status_code == 202
    data = response.json()
    assert data["scenarioId"] == scenario_id
    assert data["scenarioName"] == scenario_name
    assert data["status"] == "Running"
    assert data["inputs"] is None
    assert data["logs"] == ["Test run initiated via API."]

    mock_add_task.assert_called_once_with(
        mock_execute_scenario,
        scenario_def,
        ANY, # TestRun object
        test_runs_db
    )


def test_run_scenario_invalid_scenario_id(): # Renamed for clarity
    response = client.post(
        "/api/scenarios/non_existent_scenario_id/run",
        json={"inputs": {"param1": "value1"}}
    )
    assert response.status_code == 404


@patch("test_automation_api.main.agent_executor", None) # Patch agent_executor to be None
def test_run_scenario_executor_not_available():
    scenario_id, _, _ = setup_scenario_for_runs()
    response = client.post(
        f"/api/scenarios/{scenario_id}/run",
        json={"inputs": {"param1": "value1"}}
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Test execution service is not available due to LLM or Agent Executor initialization failure."


# Helper to run the mocked background task immediately for testing its effect
def immediate_add_task_runner(mock_target_func):
    def runner(target_func_in_task, *args, **kwargs):
        # Simulate what BackgroundTasks would do, but immediately and await if it's async
        # The mock_target_func is what we want to run (our mock of execute_scenario)
        if asyncio.iscoroutinefunction(mock_target_func):
            # This is tricky with TestClient as it has its own event loop handling.
            # For synchronous mocks or mocks that we can await from test:
            # asyncio.run(mock_target_func(*args, **kwargs))
            # Simplification: Assume mock_target_func can be called directly
            # If it's an async MagicMock, its return value is an awaitable, but the mock itself isn't async.
            # This part needs careful handling if the mock is truly async.
            # For this test structure, we'll assume the mock can be called directly.
            # If the original `execute_scenario` is async, the MagicMock will be too.
            # We will make our test mocks synchronous for simplicity here.
            mock_target_func(*args, **kwargs) # Call the mock directly
        else:
            mock_target_func(*args, **kwargs) # Call the mock directly
    return runner


async def mock_execute_successful(scenario_def, test_run_obj, db_list):
    # Simulate finding the object in db_list and updating it
    # This is crucial: test_run_obj passed here is the one from test_runs_db
    print(f"Mock execute_successful called for run ID: {test_run_obj.id}")
    test_run_obj.status = "Completed"
    test_run_obj.logs.append("Agent finished successfully.")
    test_run_obj.endTime = datetime.now(timezone.utc)
    test_run_obj.resultsSummary = "Mock success summary."
    print(f"Mock updated run ID {test_run_obj.id} to status {test_run_obj.status}")


async def mock_execute_failure(scenario_def, test_run_obj, db_list):
    print(f"Mock execute_failure called for run ID: {test_run_obj.id}")
    test_run_obj.status = "Failed"
    test_run_obj.logs.append("Agent failed.")
    test_run_obj.endTime = datetime.now(timezone.utc)
    test_run_obj.resultsSummary = "Mock failure summary."
    print(f"Mock updated run ID {test_run_obj.id} to status {test_run_obj.status}")


@patch("test_automation_api.main.BackgroundTasks.add_task")
@patch("test_automation_api.main.agent_executor.execute_scenario", new_callable=MagicMock)
def test_run_scenario_updates_run_status_success(mock_execute_scenario_patch: MagicMock, mock_add_task_patch: MagicMock):
    scenario_id, _, _ = setup_scenario_for_runs()
    
    # Configure the mock add_task to run our "successful" mock execute_scenario immediately
    # And make our mock_execute_scenario_patch (the one agent_executor.execute_scenario is patched with)
    # point to our async helper.
    mock_execute_scenario_patch.side_effect = mock_execute_successful 
    
    # This is the tricky part with TestClient. BackgroundTasks are run *after* the response is sent.
    # We cannot easily make it "immediate" in the same way as with a direct function call.
    # The TestClient handles running these tasks. We rely on that behavior.
    # The mock_execute_successful will be picked up by the BackgroundTasks system of TestClient.

    response = client.post(f"/api/scenarios/{scenario_id}/run", json={})
    assert response.status_code == 202
    run_id = response.json()["id"]

    # Allow event loop to process the task. TestClient should do this.
    # Forcing it can be done by entering/exiting context or small sleep for real async.
    # With TestClient, background tasks are usually executed before the client returns.
    # Let's verify by fetching the run.
    
    # Wait for a short period to allow the background task to execute (if truly async)
    # This is generally not ideal for unit tests but can be a pragmatic way for TestClient
    # asyncio.run(asyncio.sleep(0.05)) # This won't work directly in a sync pytest func

    # Check the run status by fetching it
    updated_run_response = client.get(f"/api/runs/{run_id}")
    assert updated_run_response.status_code == 200
    updated_run_data = updated_run_response.json()
    
    assert updated_run_data["status"] == "Completed"
    assert "Agent finished successfully." in updated_run_data["logs"]
    assert updated_run_data["resultsSummary"] == "Mock success summary."
    assert updated_run_data["endTime"] is not None


@patch("test_automation_api.main.BackgroundTasks.add_task")
@patch("test_automation_api.main.agent_executor.execute_scenario", new_callable=MagicMock)
def test_run_scenario_updates_run_status_failure(mock_execute_scenario_patch: MagicMock, mock_add_task_patch: MagicMock):
    scenario_id, _, _ = setup_scenario_for_runs()
    mock_execute_scenario_patch.side_effect = mock_execute_failure

    response = client.post(f"/api/scenarios/{scenario_id}/run", json={})
    assert response.status_code == 202
    run_id = response.json()["id"]

    updated_run_response = client.get(f"/api/runs/{run_id}")
    assert updated_run_response.status_code == 200
    updated_run_data = updated_run_response.json()

    assert updated_run_data["status"] == "Failed"
    assert "Agent failed." in updated_run_data["logs"]
    assert updated_run_data["resultsSummary"] == "Mock failure summary."
    assert updated_run_data["endTime"] is not None


def test_get_all_runs():
    scenario_id, _, _ = setup_scenario_for_runs()
    # These will now be background tasks. The immediate GET might show "Running".
    # For this test, we're just checking if runs are added to the list.
    # The status update tests cover the change from Running -> Completed/Failed.
    client.post(f"/api/scenarios/{scenario_id}/run", json={"inputs": {"run": "1"}})
    client.post(f"/api/scenarios/{scenario_id}/run", json={"inputs": {"run": "2"}})

    response = client.get("/api/runs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2 # Could be more if other tests ran and didn't clean up perfectly, but fixture should handle


def test_get_runs_for_scenario():
    scenario_id, _ = setup_scenario_for_runs()
    # Create some runs for this scenario
    client.post(f"/api/scenarios/{scenario_id}/run", json={"inputs": {"run": "s1r1"}})
    client.post(f"/api/scenarios/{scenario_id}/run", json={"inputs": {"run": "s1r2"}})

    # Create another scenario and its run, to ensure filtering works
    other_scenario_res = client.post("/api/scenarios", json={"name": "Other Scenario", "description": "Other", "scenarioDefinition": "{'type':'other'}"})
    other_scenario_id = other_scenario_res.json()["id"]
    client.post(f"/api/scenarios/{other_scenario_id}/run", json={"inputs": {"run": "s2r1"}})
    
    response = client.get(f"/api/scenarios/{scenario_id}/runs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2 # Only runs for the specified scenario
    for run in data:
        assert run["scenarioId"] == scenario_id


def test_get_runs_for_invalid_scenario():
    response = client.get("/api/scenarios/non_existent_scenario_id/runs")
    assert response.status_code == 404


def test_get_run_by_id():
    scenario_id, _ = setup_scenario_for_runs()
    create_run_response = client.post(
        f"/api/scenarios/{scenario_id}/run",
        json={"inputs": {"detail": "fetch_me"}}
    )
    run_id = create_run_response.json()["id"]
    
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == run_id
    assert data["inputs"] == {"detail": "fetch_me"}


def test_get_run_not_found():
    response = client.get("/api/runs/non_existent_run_id")
    assert response.status_code == 404

# Edge cases and error conditions

def test_create_scenario_invalid_data():
    # Missing 'name' which is required by StrictTestScenarioCreate
    response = client.post(
        "/api/scenarios",
        json={"description": "Missing name", "scenarioDefinition": "{}"}
    )
    assert response.status_code == 422 # Unprocessable Entity


def test_update_scenario_empty_payload():
    # Create a scenario first
    create_response = client.post(
        "/api/scenarios",
        json={"name": "Test Empty Update", "description": "Initial", "scenarioDefinition": "{'type':'empty_update_test'}"}
    )
    scenario_id = create_response.json()["id"]

    # Send an empty JSON object for update
    response = client.put(
        f"/api/scenarios/{scenario_id}",
        json={} # Empty payload
    )
    # The main.py has a check for `if not update_data: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST`
    assert response.status_code == 400 
    assert response.json()["detail"] == "No update data provided"

# Note: More tests for invalid data (e.g., wrong types) could be added.
# FastAPI's automatic validation handles many of these, resulting in 422s.
# TestClient raises an exception for 422 by default, which is fine.
# To explicitly test the 422 response body, you'd catch the exception or configure TestClient.
# For now, confirming the 422 status code is sufficient for this example.

# Example for testing 422 content if needed:
# from fastapi import HTTPException as FastAPIHTTPException
# def test_create_scenario_explicit_422():
#     with pytest.raises(FastAPIHTTPException) as excinfo: # This is not correct, TestClient does not raise FastAPIHTTPException
        # client.post("/api/scenarios", json={"description": "x"}) # This will be handled by pydantic validation
    # This needs to be handled by checking response directly as shown above.
    # The TestClient does not re-raise the server-side HTTPException for 422s from Pydantic validation.
    # It returns a response object with status_code 422.
    pass
