import numpy as np
import pytest
from shapely.geometry import box

from pipeline import rift3d


def test_grid_axes_match_spec():
    lons, lats = rift3d.grid_axes()
    assert len(lons) == 2101 and len(lats) == 401
    assert lons[0] == -65.0 and round(float(lons[-1]), 6) == 40.0
    assert lats[0] == -20.0 and round(float(lats[-1]), 6) == -40.0  # de norte a sul


def test_decode_terrarium_known_values():
    rgb = np.array([[[128, 0, 0], [127, 255, 0], [130, 10, 128]]], dtype=np.uint8)
    assert rift3d.decode_terrarium(rgb).tolist() == [[0.0, -1.0, 522.5]]


def test_tile_xy_origin_and_antimeridian():
    assert rift3d.tile_xy(0.0, 0.0, 1) == (1.0, 1.0)
    assert rift3d.tile_xy(-180.0, 0.0, 1)[0] == 0.0


def test_sample_heights_outside_mosaic_is_nodata():
    mosaic = np.zeros((256, 256), dtype=np.float32)
    h = rift3d.sample_heights(mosaic, 0, 0, 5, np.array([170.0]), np.array([-30.0]))
    assert h[0, 0] == rift3d.NODATA


def test_sample_heights_inside_mosaic_reads_pixel():
    mosaic = np.full((256, 256), 123.4, dtype=np.float32)
    # (lon 0, lat 0) em z=5 cai no tile x=16,y=16: mosaico que comeca em (16,16)
    h = rift3d.sample_heights(mosaic, 16, 16, 5, np.array([0.01]), np.array([-0.01]))
    assert h[0, 0] == 123


def test_plate_raster_first_match_wins_and_zero_outside():
    a = (201, box(0, 0, 2, 2))
    b = (999, box(1, 0, 3, 2))
    r = rift3d.plate_raster([a, b], np.array([0.5, 1.5, 2.5, 9.0]), np.array([1.0]))
    assert r.tolist() == [[201, 201, 999, 0]]


def test_plate_raster_accepts_plate_ids_above_uint16():
    # o modelo Merdith tem IDs como 77013
    r = rift3d.plate_raster([(77013, box(0, 0, 2, 2))], np.array([1.0]), np.array([1.0]))
    assert r.tolist() == [[77013]]


def test_mask_deep_removes_plate_below_cutoff_and_keeps_nodata_rule():
    plates = np.array([[201, 201, 201, 701]], dtype=np.uint32)
    heights = np.array([[100, -2500, -2501, rift3d.NODATA]], dtype=np.int16)
    out = rift3d.mask_deep(plates, heights, -2500)
    assert out.tolist() == [[201, 201, 0, 0]]   # abaixo do corte e sem altura ficam sem placa
    assert plates[0, 2] == 201                  # nao altera a entrada


def test_choose_fixed_uses_east_columns_only():
    plates = np.array([[201, 201, 701, 701, 701, 0]], dtype=np.uint16)
    assert rift3d.choose_fixed(plates, np.array([-50, -10, 5, 10, 20, 30.0])) == 701
    with pytest.raises(ValueError):
        rift3d.choose_fixed(np.array([[201, 201]], dtype=np.uint16), np.array([-50.0, -40.0]))
