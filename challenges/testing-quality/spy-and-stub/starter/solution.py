class Call:
    """Record of one spy invocation: ``args`` tuple and ``kwargs`` dict."""

    def __init__(self, args=(), kwargs=None):
        # TODO: store the positional tuple and a copy of the keyword mapping.
        raise NotImplementedError("Complete the Call record")


class Spy:
    """Test double that records calls and optionally stubs its result."""

    def __init__(self, target=None):
        # TODO: store ``target``, ``return_value`` (None) an empty ``side_effect``
        # list and an empty call history.
        raise NotImplementedError("Complete the Spy test double")

    def __call__(self, *args, **kwargs):
        # TODO: record the call, then apply side_effect -> target -> return_value.
        raise NotImplementedError("Complete the Spy __call__ method")

    @property
    def calls(self):
        """Return a fresh list of the recorded :class:`Call` objects."""
        raise NotImplementedError("Complete the calls property")

    @property
    def call_count(self):
        """Return how many calls were recorded."""
        raise NotImplementedError("Complete the call_count property")

    def assert_called_once(self):
        """Raise ``AssertionError`` unless exactly one call was recorded."""
        raise NotImplementedError("Complete the assert_called_once method")

    def assert_called_with(self, *args, **kwargs):
        """Raise ``AssertionError`` if the last call does not match."""
        raise NotImplementedError("Complete the assert_called_with method")

    def assert_not_called(self):
        """Raise ``AssertionError`` if any call was recorded."""
        raise NotImplementedError("Complete the assert_not_called method")

    def reset(self):
        """Clear the recorded calls while keeping the configuration."""
        raise NotImplementedError("Complete the reset method")
