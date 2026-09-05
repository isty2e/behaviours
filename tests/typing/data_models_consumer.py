from typing import assert_type

from data_models import AttrReading, Box, DataReading, Named

assert_type(DataReading(3), DataReading)
assert_type(DataReading(raw=3).doubled(), int)
assert_type(DataReading(3).same_type(), DataReading)
assert_type(AttrReading(3), AttrReading)
assert_type(AttrReading(raw=3).doubled(), int)
assert_type(AttrReading(3).same_type(), AttrReading)
assert_type(Box[int](3).boxed(), list[int])
assert_type(Box[str]("x").item(), str)
assert_type(Named("abc").upper(), str)
assert DataReading(3).doubled() == AttrReading(3).doubled() == 6
assert Named("abc").upper() == "ABC"
