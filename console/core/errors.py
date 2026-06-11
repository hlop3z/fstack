class ConsoleError(Exception):
    """Base for all core errors. Adapters map subclasses to exit codes / HTTP statuses."""


class UnknownAction(ConsoleError):
    pass


class InvalidParam(ConsoleError):
    pass


class TargetBusy(ConsoleError):
    pass


class ConfirmationRequired(ConsoleError):
    pass


class UnknownJob(ConsoleError):
    pass


class InventoryUnavailable(ConsoleError):
    """The target repo's inventory could not be loaded (ansible-inventory failed/missing)."""
