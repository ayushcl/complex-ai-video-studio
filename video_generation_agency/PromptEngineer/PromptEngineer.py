from pathlib import Path

from agency_swarm import Agent

from ..settings import get_model_name

AGENT_DIR = Path(__file__).parent

prompt_engineer = Agent(
    name="PromptEngineer",
    description=(
        "Converts approved production briefs into clean, model-ready video "
        "generation prompts."
    ),
    instructions=str(AGENT_DIR / "instructions.md"),
    files_folder=str(AGENT_DIR / "files"),
    schemas_folder=str(AGENT_DIR / "schemas"),
    tools_folder=str(AGENT_DIR / "tools"),
    model=get_model_name(),
)
