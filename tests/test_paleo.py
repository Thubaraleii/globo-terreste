from pipeline import paleo


def test_ages_default_range():
    a = paleo.ages()
    assert a[0] == 0 and a[-1] == 150 and len(a) == 31


def test_ring_closes_and_uses_lon_lat():
    class P:
        def __init__(self, lat, lon):
            self.lat, self.lon = lat, lon

        def get_latitude(self):
            return self.lat

        def get_longitude(self):
            return self.lon

    ring = paleo._ring([P(10, 20), P(11, 21), P(12, 22)])
    assert ring[0] == [20, 10] and ring[-1] == ring[0]


def test_model_has_licence_and_citation():
    assert paleo.MODEL["licence"] == "CC BY 4.0" and "Merdith" in paleo.MODEL["citation"]
