"""Portable public package for HarnessRelay configuration and setup."""

__version__ = "0.1.0a1"

from .configuration import (
    ADAPTER_REGISTRY,
    AdapterSpec,
    ConfigurationError,
    RelayConfig,
    SUPPORTED_ADAPTERS,
    SUPPORTED_CONFIG_VERSION,
    UserPaths,
    WorkerConfig,
    default_config,
    load_config,
    parse_config,
)
from .adapters import (
    AdapterError,
    Invocation,
    TaskRequest,
    UnsupportedOverrideError,
    UnsupportedVersionError,
    adapter_for,
    build_invocation,
)
from .execution import ValidationRequest, run_task
from .results import (
    RESULT_SCHEMA_VERSION,
    NativeReport,
    ResultValidationError,
    build_result,
    packaged_result_schema,
    parse_native_output,
    validate_result,
)
from .git_evidence import GitEvidenceError, capture_base, capture_snapshot

__all__ = [
    "__version__",
    "AdapterSpec",
    "ADAPTER_REGISTRY",
    "ConfigurationError",
    "RelayConfig",
    "SUPPORTED_ADAPTERS",
    "SUPPORTED_CONFIG_VERSION",
    "UserPaths",
    "WorkerConfig",
    "default_config",
    "load_config",
    "parse_config",
    "AdapterError",
    "Invocation",
    "TaskRequest",
    "UnsupportedOverrideError",
    "UnsupportedVersionError",
    "adapter_for",
    "build_invocation",
    "ValidationRequest",
    "run_task",
    "RESULT_SCHEMA_VERSION",
    "NativeReport",
    "ResultValidationError",
    "build_result",
    "packaged_result_schema",
    "parse_native_output",
    "validate_result",
    "GitEvidenceError",
    "capture_base",
    "capture_snapshot",
]
