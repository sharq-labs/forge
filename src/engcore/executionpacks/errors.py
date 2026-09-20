"""Execution-pack contract errors."""


class ExecutionPackError(Exception):
    """Base error for execution-pack infrastructure."""


class InvalidExecutionPackManifest(ExecutionPackError):
    """An execution manifest is malformed."""


class InvalidExecutionPackProvider(ExecutionPackError):
    """Provider factories disagree with their manifest."""


class ExecutionDependencyError(ExecutionPackError):
    """Required composition/domain authority is unavailable or mismatched."""


class DuplicateExecutionPack(ExecutionPackError):
    """Duplicate exact execution-pack identity."""


class ExecutionPackNotFound(ExecutionPackError):
    """Requested execution pack is not registered."""


class ExecutionPackNotEnabled(ExecutionPackError):
    """Requested execution pack is registered but not enabled."""
