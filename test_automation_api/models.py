import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal

from pydantic import BaseModel, Field, HttpUrl

class TestScenario(BaseModel):
    id: str = Field(default_factory=lambda: f"scenario-{uuid.uuid4()}")
    name: str
    description: str
    scenarioDefinition: str  # JSON string
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

class TestRun(BaseModel):
    id: str = Field(default_factory=lambda: f"run-{uuid.uuid4()}")
    scenarioId: str
    scenarioName: str
    startTime: datetime = Field(default_factory=datetime.utcnow)
    endTime: Optional[datetime] = None
    status: Literal["Pending", "Running", "Completed", "Failed"]
    logs: List[str] = Field(default_factory=list)
    resultsSummary: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None
    output: Optional[Any] = None
