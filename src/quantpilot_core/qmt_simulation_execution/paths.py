"""Safe filesystem locations for one immutable intent identity."""

from __future__ import annotations

import re
import stat
from pathlib import Path

from .constants import (
    ACKNOWLEDGEMENTS_RELATIVE_PATH,
    ACCOUNT_BINDING_KEY_RELATIVE_PATH,
    INTENTS_RELATIVE_PATH,
    MAX_INTENT_ID_LENGTH,
    STATE_RELATIVE_PATH,
)
from .errors import InvalidBridgeRootError, InvalidIntentError, RepositoryLocalPathError


_INTENT_ID_PATTERN = re.compile(
    rf"\A[A-Za-z0-9][A-Za-z0-9_-]{{0,{MAX_INTENT_ID_LENGTH - 1}}}\Z"
)


def validate_intent_id(value: object) -> str:
    if not isinstance(value, str) or _INTENT_ID_PATTERN.fullmatch(value) is None:
        raise InvalidIntentError("intent_id is outside the safe protocol shape")
    return value


def normalized_bridge_root(bridge_root: str | Path) -> Path:
    if not isinstance(bridge_root, (str, Path)):
        raise InvalidBridgeRootError("bridge root must be a filesystem path")
    try:
        path = Path(bridge_root).expanduser()
    except (TypeError, ValueError, OSError) as exc:
        raise InvalidBridgeRootError("bridge root must be a filesystem path") from exc
    if not str(path).strip():
        raise InvalidBridgeRootError("bridge root must be a non-empty filesystem path")
    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise InvalidBridgeRootError("bridge root cannot be resolved safely") from exc


def reject_repository_local_bridge_root(
    bridge_root: str | Path,
    *,
    repository_root: str | Path | None = None,
) -> Path:
    """Reject a bridge root nested under any discoverable Git worktree."""

    root = normalized_bridge_root(bridge_root)
    for candidate in (root, *root.parents):
        try:
            marker = candidate / ".git"
            if marker.exists() or marker.is_symlink():
                raise RepositoryLocalPathError(
                    "execution artifacts must not be located inside a Git repository",
                    path=root,
                )
        except OSError as exc:
            raise InvalidBridgeRootError(
                "bridge root repository boundary cannot be inspected safely", path=root
            ) from exc
    if repository_root is not None:
        repo = normalized_bridge_root(repository_root)
        try:
            root.relative_to(repo)
        except ValueError:
            pass
        else:
            raise RepositoryLocalPathError(
                "execution artifacts must not be located inside a Git repository",
                path=root,
            )
    return root


def reject_repository_local_artifact_path(path: str | Path) -> Path:
    """Reject one completed artifact whose resolved location is in a Git worktree."""

    try:
        resolved = Path(path).expanduser().resolve(strict=False)
    except (TypeError, ValueError, OSError, RuntimeError) as exc:
        raise InvalidBridgeRootError("artifact path cannot be resolved safely") from exc
    for candidate in (resolved.parent, *resolved.parents[1:]):
        try:
            marker = candidate / ".git"
            if marker.exists() or marker.is_symlink():
                raise RepositoryLocalPathError(
                    "execution intent must not be located inside a Git repository",
                    path=resolved,
                )
        except OSError as exc:
            raise InvalidBridgeRootError(
                "artifact repository boundary cannot be inspected safely", path=resolved
            ) from exc
    return resolved


def intent_path(bridge_root: str | Path, intent_id: str) -> Path:
    root = normalized_bridge_root(bridge_root)
    target = root / INTENTS_RELATIVE_PATH / (
        validate_intent_id(intent_id) + ".json"
    )
    return _reject_redirecting_components(root, target)


def result_path(bridge_root: str | Path, intent_id: str) -> Path:
    root = normalized_bridge_root(bridge_root)
    target = root / ACKNOWLEDGEMENTS_RELATIVE_PATH / (
        validate_intent_id(intent_id) + ".json"
    )
    return _reject_redirecting_components(root, target)


def acknowledgement_path(bridge_root: str | Path, intent_id: str) -> Path:
    return result_path(bridge_root, intent_id)


def state_path(bridge_root: str | Path, intent_id: str) -> Path:
    root = normalized_bridge_root(bridge_root)
    target = root / STATE_RELATIVE_PATH / (
        validate_intent_id(intent_id) + ".json"
    )
    return _reject_redirecting_components(root, target)


def account_binding_key_path(bridge_root: str | Path) -> Path:
    root = normalized_bridge_root(bridge_root)
    return _reject_redirecting_components(root, root / ACCOUNT_BINDING_KEY_RELATIVE_PATH)


def _reject_redirecting_components(root: Path, target: Path) -> Path:
    """Reject existing symlink components before an artifact can escape *root*."""

    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise InvalidBridgeRootError("artifact path escapes the bridge root") from exc
    current = root
    for component in relative.parts:
        current = current / component
        try:
            status = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise InvalidBridgeRootError(
                "artifact path cannot be inspected safely", path=current
            ) from exc
        if stat.S_ISLNK(status.st_mode):
            raise InvalidBridgeRootError(
                "artifact path must not contain symbolic links", path=current
            )
    return target
