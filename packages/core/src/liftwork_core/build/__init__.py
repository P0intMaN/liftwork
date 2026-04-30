"""Build engine: language detection, Dockerfile generation, executor protocols."""

from liftwork_core.build.config import (
    BuildSpec,
    DeploySpec,
    LiftworkConfig,
    Resources,
    load_liftwork_config,
)
from liftwork_core.build.language import Language, detect_language
from liftwork_core.build.protocols import (
    BuildContext,
    BuildExecutor,
    BuildResult,
    LogSink,
)
from liftwork_core.build.renderer import (
    DEFAULT_TEMPLATES,
    DockerfileTemplateError,
    render_dockerfile,
)

__all__ = [
    "DEFAULT_TEMPLATES",
    "BuildContext",
    "BuildExecutor",
    "BuildResult",
    "BuildSpec",
    "DeploySpec",
    "DockerfileTemplateError",
    "Language",
    "LiftworkConfig",
    "LogSink",
    "Resources",
    "detect_language",
    "load_liftwork_config",
    "render_dockerfile",
]
