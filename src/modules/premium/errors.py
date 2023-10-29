class GemTransactionFailed(Exception):
    """
    Base exception class used when a gem transaction failed.
    """
    pass


class BalanceTooLow(GemTransactionFailed):
    """
    Exception raised when transaction results in a negative gem balance.
    """
    pass


class BalanceTooHigh(GemTransactionFailed):
    """
    Exception raised when transaction results in gem balance overflow.
    """
    pass
