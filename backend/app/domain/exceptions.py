
class WorkflowExecutionError(Exception):
    """Base class for expected workflow failures."""

    error_code = "WORKFLOW_ERROR"


class TransientWorkflowError(WorkflowExecutionError):
    """Temporary failure known to have no side effect."""

    error_code = "TRANSIENT_ERROR"


class PermanentWorkflowError(WorkflowExecutionError):
    """Failure that cannot be fixed by simply retrying."""

    error_code = "PERMANENT_ERROR"


class UncertainOutcomeError(WorkflowExecutionError):
    """Operation may have succeeded before its response was lost."""

    error_code = "UNCERTAIN_OUTCOME"
