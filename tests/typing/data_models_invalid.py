from data_models import AttrReading, Box, DataReading, Named

DataReading("wrong")
AttrReading("wrong")
Box[int]("wrong")
Named(7)
DataReading(1).raw = 2
bad: str = AttrReading(2).doubled()
