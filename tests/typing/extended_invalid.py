from extended_api import Child, Combined, Decode, FixedUser, Number, Selected, TextEcho
from typing_extensions import override

Number.from_bytes("wrong")  # expected: bad-argument-type
Child.from_text(3)  # expected: bad-argument-type
Number.parse(3)  # expected: bad-argument-type
Number(1).parse([])  # expected: bad-argument-type
Selected().render(3)  # expected: bad-argument-type
Selected.parse(3)  # expected: bad-argument-type
Combined().upper(1)  # expected: bad-argument-count
Combined.parse([])  # expected: bad-argument-type
Decode()  # expected: bad-instantiation


class WrongFinal(FixedUser):
    @override
    def stable(self) -> int:  # expected: bad-override
        return 2


class WrongReturn(Decode):
    @classmethod
    @override
    def from_text(cls, text: str, /) -> int:  # expected: bad-override
        return 3


TextEcho.echo(3)  # expected: bad-argument-type
