# VEO Audio Production Pipeline

Agency Swarm project for the Ayush's video generation pipeline.

## Operator UI

An internal operator console wraps the packet adapter
(`video_generation_agency/run_from_packet.py`) with job setup, voice
audition & pick, free dry-run previews, and double-gated live runs. It needs
no extra dependencies:

```bash
python ui/server.py
```

Then open <http://127.0.0.1:8765>. See [ui/README.md](ui/README.md) for the
screens, the spend-safety model, and the smoke tests.

## Agency

The agency is organized around five roles:

- `CreativeDirector`
- `PromptEngineer`
- `VideoGenerator`
- `AssetManager`
- `QAReviewer`

## Local Setup

Use Python 3.10 or newer. The local macOS system `python3` may be too old for
the current Agency Swarm/OpenAI Agents stack, so prefer Python 3.12 when
available.

Create and activate a virtual environment from the project root:

```bash
python3.12 -m venv venv
source venv/bin/activate
```

Install the Agency Swarm dependencies:

```bash
pip install -r video_generation_agency/requirements.txt
```

Create your local environment file:

```bash
cp .env.example .env
```

Edit `.env` and replace `your-gemini-api-key` with your real Gemini API key:

```bash
GEMINI_API_KEY=your-real-gemini-api-key
AGENCY_MODEL=gemini-2.5-flash
```

`GEMINI_API_KEY` is the key name LiteLLM expects for Gemini. `AGENCY_MODEL`
should be the plain Gemini model name; the code adds the Agency Swarm
`litellm/gemini/` prefix internally.

## Verify Setup

Check that the agency imports without making a live model call:

```bash
python -c "from video_generation_agency.agency import agency; print('Agency ready')"
```

After adding your real Gemini API key, run one live Gemini smoke test:

```bash
python scripts/test_gemini_connection.py
```

The expected final line is:

```text
Gemini connection OK
```

## Veo Proof Script

A standalone Veo proof script is available at
`video_generation_agency/proof_veo_call.py`. It submits exactly one Veo request
and saves `proof_output.mp4`, but do not run it until you are ready for possible
paid API usage and have confirmed billing/model access:

```bash
python video_generation_agency/proof_veo_call.py
```

## Run the Agency

Start the Python-backed terminal UI:

```bash
python -m video_generation_agency.agency
```

You can also use the Agency Swarm terminal launcher from the project root:

```bash
npx @vrsen/agentswarm
```

The live Gemini test should be run only after `.env` contains a valid
`GEMINI_API_KEY`.
