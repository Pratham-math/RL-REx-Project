from ..types import Comparator


def compare(actual: str, expected: str, comparator: Comparator) -> bool:
    if comparator == "tokens_v1":
        return actual.split() == expected.split()
    if comparator == "text_v1":
        return actual == expected
    if comparator == "lines_v1":
        # Ignore exactly one final newline; preserve spaces and blank lines.
        return actual.removesuffix("\n").split("\n") == expected.removesuffix("\n").split("\n")
    raise ValueError("Unknown comparator")
