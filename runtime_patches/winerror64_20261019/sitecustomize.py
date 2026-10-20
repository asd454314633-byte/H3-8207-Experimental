import hashlib
import importlib.util
import os
import sys
from pathlib import Path

# Install only inside the registered h3-lab 8207 ComfyUI server process.
if (os.environ.get("H3_INSTANCE_ID") == "h3-lab"
        and Path(sys.argv[0]).name.lower() == "main.py"
        and "--port" in sys.argv
        and sys.argv[sys.argv.index("--port") + 1] == "8207"):
    candidate = Path(__file__).with_name("accept_candidate.py")
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest().upper()
    expected = "0A1D8ADA0819B60D94A5B0E7B680D0268AC5E92AEA7434ED24BF28AF4F2984E4"
    if digest != expected:
        raise RuntimeError("8207 IOCP repair candidate SHA256 mismatch: " + digest)
    spec = importlib.util.spec_from_file_location("h3_8207_winerror64_accept_candidate", candidate)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the 8207 IOCP repair candidate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    fingerprints = module.verify_source()
    module.install()
    print("H3_8207_IOCP_ACCEPT_REPAIR=INSTALLED candidate_sha256=" + digest
          + " source_fingerprints=" + repr(fingerprints), flush=True)
