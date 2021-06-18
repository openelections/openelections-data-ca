import re
from abc import ABC, abstractmethod


class FormatTest(ABC):
    @property
    @abstractmethod
    def passed(self) -> bool:
        pass

    @abstractmethod
    def get_failure_message(self, max_examples: int) -> str:
        pass

    @abstractmethod
    def test(self, value):
        pass


# noinspection PyAbstractClass
class RowTest(FormatTest):
    def __init__(self):
        super().__init__()
        self.__current_row = 0

    @property
    def current_row(self) -> int:
        return self.__current_row

    @current_row.setter
    def current_row(self, value: int):
        self.__current_row = value


class ValueTest(RowTest):
    def __init__(self):
        super().__init__()
        self.__failures = {}

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    def passed(self):
        return len(self.__failures) == 0

    def get_failure_message(self, max_examples=10):
        message = f"There are {len(self.__failures)} rows that have entries with {self.description}:\n"
        count = 1
        for key, value in self.__failures.items():
            message += f"\n\tRow {key}: {value}"
            count += 1
            if count > max_examples:
                message += f"\n\t[Truncated to {max_examples} examples]"
                break

        return message

    @abstractmethod
    def is_bad_value(self, value) -> bool:
        pass

    def test(self, row):
        for entry in row:
            if self.is_bad_value(entry):
                self.__failures[self.current_row] = row
                break


class EmptyHeaders(FormatTest):
    def __init__(self):
        super().__init__()
        self.__headers = []
        self.__passed = False

    @property
    def passed(self) -> bool:
        return self.__passed

    def get_failure_message(self, max_examples=0):
        return f"Header {self.__headers} has empty entries."

    def test(self, headers: list[str]):
        self.__headers = headers
        self.__passed = "" not in headers


class LowercaseHeaders(FormatTest):
    def __init__(self):
        super().__init__()
        self.__headers = []
        self.__passed = False

    @property
    def passed(self) -> bool:
        return self.__passed

    def get_failure_message(self, max_examples=0):
        return f"Header {self.__headers} should only contain lowercase characters."

    def test(self, headers: list[str]):
        self.__headers = headers
        self.__passed = headers == [x.lower() for x in headers]


class MissingHeaders(FormatTest):
    def __init__(self, required_headers: set[str]):
        super().__init__()
        self.__headers = []
        self.__passed = False
        self.__required_headers = required_headers

    @property
    def passed(self) -> bool:
        return self.__passed

    def get_failure_message(self, max_examples=0):
        return f"Header {self.__headers} is missing entries: {self.__required_headers.difference(self.__headers)}."

    def test(self, headers: list[str]):
        self.__headers = headers
        self.__passed = self.__required_headers.issubset(headers)


class UnknownHeaders(FormatTest):
    def __init__(self):
        super().__init__()
        self.__headers = []
        self.__passed = False

    @property
    def passed(self) -> bool:
        return self.__passed

    def get_failure_message(self, max_examples=0):
        return f"Header {self.__headers} has unknown entries."

    def test(self, headers: list[str]):
        self.__headers = headers
        self.__passed = "unknown" not in [x.strip().lower() for x in headers]


class ConsecutiveSpaces(ValueTest):
    regex = re.compile(r"\s{2,}")

    @property
    def description(self):
        return "consecutive whitespace characters"

    def is_bad_value(self, value):
        return bool(ConsecutiveSpaces.regex.search(value))


class EmptyRows(RowTest):
    regex = re.compile(r"\S")

    def __init__(self):
        super().__init__()
        self.__empty_row_count = 0

    @property
    def passed(self):
        return self.__empty_row_count == 0

    def get_failure_message(self, max_examples=0):
        return f"Has {self.__empty_row_count} empty rows."

    def test(self, row: list):
        has_content = False
        for entry in row:
            has_content |= bool(EmptyRows.regex.search(entry))

        if not has_content:
            self.__empty_row_count += 1


class InconsistentNumberOfColumns(RowTest):
    def __init__(self, headers):
        super().__init__()
        self.__failures = {}
        self.__headers = headers

    @property
    def passed(self) -> bool:
        return len(self.__failures) == 0

    def get_failure_message(self, max_examples=10) -> str:
        message = f"Header {self.__headers} has {len(self.__headers)} entries, but there are {len(self.__failures)} " \
                  f"rows with an inconsistent number of columns:\n"
        count = 1
        for key, value in self.__failures.items():
            message += f"\n\tRow {key} ({len(value)} entries): {value}"
            count += 1
            if count > max_examples:
                message += f"\n\t[Truncated to {max_examples} examples]"
                break

        return message

    def test(self, row: list):
        if len(row) != len(self.__headers):
            self.__failures[self.current_row] = row


class LeadingAndTrailingSpaces(ValueTest):
    @property
    def description(self):
        return "leading or trailing whitespace characters"

    def is_bad_value(self, value):
        return value != value.strip()


class NonAlphanumericEntries(ValueTest):
    regex = re.compile(r"\w")

    @property
    def description(self):
        return "only non-alphanumeric characters"

    def is_bad_value(self, value):
        return value != "" and not bool(NonAlphanumericEntries.regex.search(value))


class PrematureLineBreaks(ValueTest):
    @property
    def description(self):
        return "newline characters"

    def is_bad_value(self, value):
        return "\n" in value
