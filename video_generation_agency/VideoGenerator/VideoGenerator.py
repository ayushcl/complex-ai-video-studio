from pathlib import Path

from agency_swarm import Agent

from ..settings import get_model_name

AGENT_DIR = Path(__file__).parent

video_generator = Agent(
    name="VideoGenerator",
    description=(
        "Executes approved video generation requests with available API tools "
        "and returns structured generation results."
    ),
    instructions=str(AGENT_DIR / "instructions.md"),
    files_folder=str(AGENT_DIR / "files"),
    schemas_folder=str(AGENT_DIR / "schemas"),
    tools_folder=str(AGENT_DIR / "tools"),
    model=get_model_name(),
)
