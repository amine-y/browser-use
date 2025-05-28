from fastapi import FastAPI, HTTPException, status, Response, BackgroundTasks
from typing import List, Optional
from datetime import datetime, timezone # Ensure timezone is imported
import uuid 
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from fastapi.responses import JSONResponse # For returning 202 with content

# Custom modules
from .models import TestScenario, TestRun # Use relative import
from .agent_executor import BrowserAgentExecutor # Import the executor
from typing import Dict, Any # For TestRunCreate inputs


# Load environment variables from .env
load_dotenv()

# Initialize the OpenAI LLM
# This will automatically pick up OPENAI_API_KEY from the environment
try:
    llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0) 
    print("Langchain OpenAI LLM initialized successfully.")
except Exception as e:
    print(f"Error initializing Langchain OpenAI LLM: {e}")
    llm = None 

# Instantiate BrowserAgentExecutor
if llm:
    try:
        agent_executor = BrowserAgentExecutor(llm=llm)
        print("BrowserAgentExecutor initialized successfully.")
    except ValueError as e: # Catch specific error from BrowserAgentExecutor constructor
        print(f"Error initializing BrowserAgentExecutor: {e}")
        agent_executor = None
    except Exception as e: # Catch any other unexpected error during initialization
        print(f"Unexpected error initializing BrowserAgentExecutor: {e}")
        agent_executor = None
else:
    agent_executor = None
    print("BrowserAgentExecutor not initialized because LLM is None.")


app = FastAPI(title="Test Automation API", version="0.1.0")

# In-memory storage
scenarios_db: List[TestScenario] = []
test_runs_db: List[TestRun] = []

# Pydantic models for request bodies
# These should inherit from BaseModel
from pydantic import BaseModel

class StrictTestScenarioCreate(BaseModel):
    name: str
    description: str
    scenarioDefinition: str # JSON string

class TestScenarioUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scenarioDefinition: Optional[str] = None
    # id, createdAt should not be updatable directly via this model
    # updatedAt will be handled by the endpoint logic

class TestRunCreate(BaseModel):
    inputs: Optional[Dict[str, Any]] = None

# Helper functions
def find_scenario_by_id(scenario_id: str) -> Optional[TestScenario]:
    for scenario in scenarios_db:
        if scenario.id == scenario_id:
            return scenario
    return None

def find_test_run_by_id(run_id: str) -> Optional[TestRun]:
    for run in test_runs_db:
        if run.id == run_id:
            return run
    return None

# --- Test Scenario Endpoints ---

@app.post("/api/scenarios", response_model=TestScenario, status_code=status.HTTP_201_CREATED)
async def create_scenario(scenario_data: StrictTestScenarioCreate):
    # ID, createdAt, updatedAt will use default_factory from TestScenario model
    new_scenario = TestScenario(
        name=scenario_data.name,
        description=scenario_data.description,
        scenarioDefinition=scenario_data.scenarioDefinition
    )
    scenarios_db.append(new_scenario)
    return new_scenario

@app.get("/api/scenarios", response_model=List[TestScenario])
async def get_scenarios():
    return scenarios_db

@app.get("/api/scenarios/{scenario_id}", response_model=TestScenario)
async def get_scenario(scenario_id: str):
    scenario = find_scenario_by_id(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    return scenario

@app.put("/api/scenarios/{scenario_id}", response_model=TestScenario)
async def update_scenario(scenario_id: str, scenario_update_data: TestScenarioUpdate):
    scenario = find_scenario_by_id(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")

    update_data = scenario_update_data.model_dump(exclude_unset=True) # Pydantic V2
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided")

    for key, value in update_data.items():
        setattr(scenario, key, value)
    
    scenario.updatedAt = datetime.utcnow() # Manually update timestamp
    return scenario

@app.delete("/api/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scenario(scenario_id: str):
    scenario_to_delete = None
    for scenario in scenarios_db:
        if scenario.id == scenario_id:
            scenario_to_delete = scenario
            break
            
    if scenario_to_delete is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    
    scenarios_db.remove(scenario_to_delete)
    return Response(status_code=status.HTTP_204_NO_CONTENT) # Ensure a Response object for 204

# Basic root endpoint from original main.py for completeness
@app.get("/")
async def root():
    return {"message": "Test Automation API"}

# To run this app (assuming /app is the current directory and venv is in /app/test_automation_api/venv):
# ./test_automation_api/venv/bin/uvicorn test_automation_api.main:app --reload --host 0.0.0.0 --port 8000
# Or, if the venv is active globally, from /app:
# uvicorn test_automation_api.main:app --reload --host 0.0.0.0 --port 8000

# --- Test Run Endpoints ---

@app.post("/api/scenarios/{scenario_id}/run", response_model=TestRun, status_code=status.HTTP_202_ACCEPTED)
async def run_scenario(
    scenario_id: str, 
    background_tasks: BackgroundTasks,
    run_create_data: Optional[TestRunCreate] = None # Make body optional, default to None
):
    if agent_executor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Test execution service is not available due to LLM or Agent Executor initialization failure."
        )

    scenario = find_scenario_by_id(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")

    # Create the TestRun object
    # id and startTime are auto-generated by Pydantic model's default_factory
    # logs default to empty list by Pydantic model
    new_run = TestRun(
        scenarioId=scenario.id,
        scenarioName=scenario.name,
        status="Running",  # Initial status set to "Running"
        inputs=run_create_data.inputs if run_create_data and run_create_data.inputs else None,
        logs=["Test run initiated via API."]  # Initial log entry
    )
    test_runs_db.append(new_run)

    # Add the agent execution to background tasks
    background_tasks.add_task(
        agent_executor.execute_scenario, 
        scenario.scenarioDefinition, 
        new_run, 
        test_runs_db
    )
    
    # Return the TestRun model, FastAPI will handle serialization.
    # Using JSONResponse to explicitly set 202 status and ensure model is dumped correctly.
    return JSONResponse(content=new_run.model_dump(mode='json'), status_code=status.HTTP_202_ACCEPTED)


@app.get("/api/runs", response_model=List[TestRun])
async def get_all_runs():
    return test_runs_db

@app.get("/api/scenarios/{scenario_id}/runs", response_model=List[TestRun])
async def get_runs_for_scenario(scenario_id: str):
    scenario = find_scenario_by_id(scenario_id)
    if scenario is None:
        # Ensure scenario exists before trying to list its runs
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    
    runs_for_scenario = [run for run in test_runs_db if run.scenarioId == scenario_id]
    return runs_for_scenario

@app.get("/api/runs/{run_id}", response_model=TestRun)
async def get_run_details(run_id: str):
    test_run = find_test_run_by_id(run_id)
    if test_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test run not found")
    return test_run
