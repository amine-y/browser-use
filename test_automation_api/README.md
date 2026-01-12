# Test Automation API

This API provides services for managing and executing browser-based test scenarios using an AI-powered agent.

## Features

-   CRUD operations for Test Scenarios.
-   Execution of Test Scenarios via an AI agent.
-   Tracking of Test Run history, status, and logs.

## Setup

1.  **Prerequisites**:
    *   Python 3.8+
    *   Access to an OpenAI API key.

2.  **Installation**:
    *   Ensure all dependencies are installed from `requirements.txt`:
        ```bash
        pip install -r requirements.txt
        ```
    *   The `browser_use` library and its dependencies (like Playwright) are also required. Playwright might need to download browser binaries on first use:
        ```bash
        playwright install
        ```

3.  **Environment Variables**:
    *   This service requires an OpenAI API key to function.
    *   Create a `.env` file in the `test_automation_api` directory (this file should be next to `main.py`).
    *   Add your OpenAI API key to the `.env` file like this:
        ```
        OPENAI_API_KEY="your_openai_api_key_here"
        ```
    *   Replace `"your_openai_api_key_here"` with your actual OpenAI API key.

## Running the API

1.  Navigate to the `test_automation_api` directory.
2.  Run the FastAPI application using Uvicorn:
    ```bash
    uvicorn main:app --reload
    ```
3.  The API will typically be available at `http://127.0.0.1:8000`. Access the OpenAPI documentation at `http://127.0.0.1:8000/docs`.

## Usage

-   Use an API client (like Postman, curl, or a frontend application) to interact with the endpoints defined in `main.py`.
-   Key endpoints include:
    -   `/api/scenarios` (GET, POST)
    -   `/api/scenarios/{scenarioId}` (GET, PUT, DELETE)
    -   `/api/scenarios/{scenarioId}/run` (POST) - This triggers the AI agent.
    -   `/api/runs` (GET)
    -   `/api/runs/{runId}` (GET)
