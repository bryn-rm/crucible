"""Application package initialization."""

from pathlib import Path

from dotenv import load_dotenv

# Load local development settings before modules such as db/security read the
# environment. Deployment-provided variables retain precedence.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
