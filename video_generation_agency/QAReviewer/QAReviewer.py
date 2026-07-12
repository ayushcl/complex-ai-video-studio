from pathlib import Path

from agency_swarm import Agent

from ..settings import get_model_name

AGENT_DIR = Path(__file__).parent

qa_reviewer = Agent(
    name="QAReviewer",
    description=(
        "Reviews generated videos against the original brief and recommends "
        "fixes when regeneration is needed."
    ),
    instructions=str(AGENT_DIR / "instructions.md"),
    files_folder=str(AGENT_DIR / "files"),
    schemas_folder=str(AGENT_DIR / "schemas"),
    tools_folder=str(AGENT_DIR / "tools"),
    model=get_model_name(),
)
