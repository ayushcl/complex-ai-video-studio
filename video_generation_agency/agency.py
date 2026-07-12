from pathlib import Path

from agency_swarm import Agency

from .AssetManager import asset_manager
from .CreativeDirector import creative_director
from .PromptEngineer import prompt_engineer
from .QAReviewer import qa_reviewer
from .VideoGenerator import video_generator

AGENCY_DIR = Path(__file__).parent

agency = Agency(
    creative_director,
    name="Maxiion Kunisys Video Generation Agency",
    communication_flows=[
        (creative_director, prompt_engineer),
        (prompt_engineer, video_generator),
        (video_generator, asset_manager),
        (video_generator, qa_reviewer),
        (qa_reviewer, prompt_engineer),
    ],
    shared_instructions=str(AGENCY_DIR / "agency_manifesto.md"),
)


def main() -> None:
    agency.tui()


if __name__ == "__main__":
    main()
