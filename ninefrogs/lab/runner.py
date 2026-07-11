"""Challenge execution runners — subprocess pytest, docker service, docker app."""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

_PYTHON = sys.executable


@dataclass
class ExecutionResult:
    passed: int
    failed: int
    output: str
    timed_out: bool = False
    error: str = ""


# ── Docker availability (cached at import time) ───────────────────────────────

def _check_docker() -> bool:
    try:
        subprocess.run(
            ["docker", "version"],
            capture_output=True, check=True, timeout=5
        )
        return True
    except Exception:
        return False


DOCKER_AVAILABLE: bool = _check_docker()


# ── pytest subprocess runner ──────────────────────────────────────────────────

def run_pytest_challenge(
    submission_code: str,
    test_code: str,
    timeout: int = 30,
) -> ExecutionResult:
    """Write submission + test to a temp dir and run pytest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "submission.py").write_text(submission_code, encoding="utf-8")
        (tmp / "test_submission.py").write_text(test_code, encoding="utf-8")

        try:
            result = subprocess.run(
                [_PYTHON, "-m", "pytest", "test_submission.py",
                 "-v", "--tb=short", "--no-header"],
                capture_output=True, text=True,
                cwd=tmpdir, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(passed=0, failed=1,
                                   output="Timed out after %ds." % timeout,
                                   timed_out=True)

        output = result.stdout + result.stderr
        passed, failed = _parse_counts(output)
        return ExecutionResult(passed=passed, failed=failed, output=output)


def _parse_counts(output: str) -> tuple[int, int]:
    passed = len(re.findall(r" PASSED", output))
    failed = len(re.findall(r" FAILED", output))
    errors = len(re.findall(r" ERROR", output))
    if passed == 0 and failed == 0:
        m = re.search(r"(\d+) passed", output)
        if m:
            passed = int(m.group(1))
        m = re.search(r"(\d+) failed", output)
        if m:
            failed = int(m.group(1))
        m = re.search(r"(\d+) error", output)
        if m:
            errors += int(m.group(1))
    return passed, failed + errors


# ── Docker service challenges (e.g. Celery with real Redis) ──────────────────

def run_docker_service_challenge(
    submission_code: str,
    test_code: str,
    compose_file: str,
    services: list[str],
    timeout: int = 60,
) -> ExecutionResult:
    """Ensure required docker-compose services are running, then run pytest."""
    if not DOCKER_AVAILABLE:
        return ExecutionResult(passed=0, failed=1, output="",
                               error="Docker is not available on this machine.")

    # Start services (idempotent)
    up_cmd = ["docker", "compose", "-f", compose_file, "up", "-d"] + services
    subprocess.run(up_cmd, capture_output=True, timeout=30)

    return run_pytest_challenge(submission_code, test_code, timeout=timeout)


# ── Docker app challenges (ephemeral FastAPI container per submission) ────────

def run_docker_app_challenge(
    submission_code: str,
    test_code: str,
    port: int,
    base_image: str,
    requirements: list[str],
    timeout: int = 60,
) -> ExecutionResult:
    """Spin up user's code as an ephemeral container, run TestClient tests against it."""
    if not DOCKER_AVAILABLE:
        return ExecutionResult(passed=0, failed=1, output="",
                               error="Docker is not available on this machine.")

    import uuid as _uuid
    container_name = f"lab_submission_{_uuid.uuid4().hex[:8]}"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "main.py").write_text(submission_code, encoding="utf-8")
        (tmp / "test_submission.py").write_text(test_code, encoding="utf-8")

        pip_installs = " ".join(requirements)
        dockerfile = (
            f"FROM {base_image}\n"
            f"WORKDIR /app\n"
            f"RUN pip install --quiet {pip_installs}\n"
            f"COPY main.py .\n"
            f"CMD [\"uvicorn\", \"main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"{port}\"]\n"
        )
        (tmp / "Dockerfile").write_text(dockerfile, encoding="utf-8")

        image_tag = f"lab_img_{container_name}"
        try:
            build = subprocess.run(
                ["docker", "build", "-t", image_tag, "."],
                capture_output=True, text=True, cwd=tmpdir, timeout=120,
            )
            if build.returncode != 0:
                return ExecutionResult(passed=0, failed=1,
                                       output=build.stdout + build.stderr,
                                       error="Docker build failed.")

            run_proc = subprocess.run(
                ["docker", "run", "-d", "--name", container_name,
                 "-p", f"{port}:{port}", image_tag],
                capture_output=True, text=True, timeout=30,
            )
            if run_proc.returncode != 0:
                return ExecutionResult(passed=0, failed=1,
                                       output=run_proc.stderr,
                                       error="Container start failed.")

            # Poll until app is ready (max 10s)
            _wait_for_port(port, timeout=10)

            return run_pytest_challenge(submission_code, test_code, timeout=timeout)
        finally:
            subprocess.run(["docker", "rm", "-f", container_name],
                           capture_output=True, timeout=10)
            subprocess.run(["docker", "rmi", "-f", image_tag],
                           capture_output=True, timeout=30)


def _wait_for_port(port: int, timeout: int = 10) -> None:
    import socket
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.5)


# ── Rust (stub — future) ──────────────────────────────────────────────────────

def run_rust_challenge(
    submission_code: str,
    test_code: str,
    timeout: int = 60,
) -> ExecutionResult:
    return ExecutionResult(passed=0, failed=1, output="",
                           error="Rust challenges are not yet supported.")
