from dsl import *
HPC = C("astropy.coordinates.SkyCoord", Q(0, "arcsec"), Q(0, "arcsec"), obstime="2026-10-01T00:00:00", observer="earth", frame="helioprojective")
HDR = C("sunpy.map.make_fitswcs_header", IMG, HPC, scale=Q([20, 20], "arcsec/pix"), instrument="TEST", wavelength=Q(171, "Angstrom"))
SMAP = C("sunpy.map.Map", IMG, HDR)
TUP = lambda *a: {"__type__": "tuple", "items": list(a)}
DIMS = Q([50, 50], "pix")
ARGS = {
 "map": {"_args": [IMG, HDR]},
 "parse_time": {"time_string": "2026-10-12T12:00:00"}, "is_time": {"time_string": "2026-10-12"},
 "time_range_create": {"a": "2026-10-12T00:00:00", "b": "2026-10-13T00:00:00"},
 "get_earth": {"time": "2026-10-12"}, "b0": {"time": "2026-10-12"}, "l0": {"time": "2026-10-12"}, "p": {"time": "2026-10-12"},
 "angular_radius": {"t": "2026-10-12"}, "carrington_rotation_number": {"t": "2026-10-12"}, "earth_distance": {"time": "2026-10-12"},
 "true_longitude": {"t": "2026-10-12"}, "mean_obliquity_of_ecliptic": {"t": "2026-10-12"},
 "differential_rotation": {"duration": Q(5, "day"), "latitude": Q(30, "deg")},
 "get": {"key": "radius"},
 "generic_map_resample": {"dimensions": DIMS}, "generic_map_superpixel": {"dimensions": Q([2, 2], "pix")},
 "generic_map_submap": {"bottom_left": C("astropy.coordinates.SkyCoord", Q(-300, "arcsec"), Q(-300, "arcsec"), frame=C("sunpy.coordinates.Helioprojective", obstime="2026-10-01T00:00:00", observer="earth")),
                       "top_right": C("astropy.coordinates.SkyCoord", Q(300, "arcsec"), Q(300, "arcsec"), frame=C("sunpy.coordinates.Helioprojective", obstime="2026-10-01T00:00:00", observer="earth"))},
 "generic_map_world_to_pixel": {"coordinate": HPC}, "generic_map_pixel_to_world": {"x": Q(10, "pix"), "y": Q(10, "pix")},
 "make_fitswcs_header": {"data": IMG, "coordinate": HPC, "scale": Q([20, 20], "arcsec/pix")},
 "contains_full_disk": {"smap": SMAP}, "coordinate_is_on_solar_disk": {"coordinates": HPC},
 "all_coordinates_from_map": {"smap": SMAP}, "solar_angular_radius": {"coordinates": HPC},
 "generic_map_rotate": {"angle": Q(30, "deg")},
 "affine_transform": {"image": IMG, "rmatrix": ARR([[1.0, 0.0], [0.0, 1.0]])},
 "resample": {"orig": IMG, "dimensions": TUP(50, 50)},
 "reshape_image_to_4d_superpixel": {"img": IMG, "dimensions": [2, 2], "offset": [0, 0]},
 "carrington_rotation_time": {"crot": 2300}, "sky_position": {"t": "2026-10-12"},
 "eclipse_amount": {"observer": C("astropy.coordinates.SkyCoord", Q(0, "deg"), Q(0, "deg"), frame="heliographic_stonyhurst", obstime="2026-10-12")},
 "julian_centuries": {"t": "2026-10-12"},
 "get_body_heliographic_stonyhurst": {"body": "earth", "time": "2026-10-12"},
 "helioprojective_create": {"obstime": "2026-10-01T00:00:00", "observer": "earth"},
 "heliographic_stonyhurst_create": {"obstime": "2026-10-01T00:00:00"},
 "heliographic_carrington_create": {"obstime": "2026-10-01T00:00:00"},
 "solar_rotate_coordinate": {"coordinate": HPC, "time": "2026-10-02T00:00:00"},
 "sample_at_coords": {"smap": SMAP, "coordinates": HPC},
 "make_heliographic_header": {"date": "2026-10-01T00:00:00", "observer_coordinate": C("sunpy.coordinates.get_earth", "2026-10-01"), "shape": {"__type__": "tuple", "items": [128, 128]}, "frame": "carrington"},
 "print_all": {},
 "time_create": {"start": "2026-10-12", "end": "2026-10-13"},
 "instrument_create": {"value": "AIA"},
 "wavelength_create": {"wavemin": Q(171, "Angstrom"), "wavemax": Q(171, "Angstrom")},
 "level_create": {"value": 1},
 "source_create": {"value": "SDO"},
 "pixelate_coord_path": {"smap": SMAP, "coord_path": C("astropy.coordinates.SkyCoord", Q([-100, 100], "arcsec"), Q([-100, 100], "arcsec"), frame=C("sunpy.coordinates.Helioprojective", obstime="2026-10-01T00:00:00", observer="earth"))},
}
SELF = {"sunpy.map.GenericMap": SMAP}
SELECT = [
 "map","parse_time","is_time","time_range_create","julian_centuries",
 "get_earth","get_body_heliographic_stonyhurst","b0","l0","p",
 "angular_radius","carrington_rotation_number","carrington_rotation_time",
 "earth_distance","true_longitude","mean_obliquity_of_ecliptic","sky_position",
 "differential_rotation","solar_rotate_coordinate","get","print_all",
 
 "generic_map_resample","generic_map_superpixel","generic_map_submap","generic_map_rotate",
 "generic_map_world_to_pixel","generic_map_pixel_to_world",
 "make_fitswcs_header","make_heliographic_header",
 "contains_full_disk","coordinate_is_on_solar_disk","all_coordinates_from_map",
 "solar_angular_radius","pixelate_coord_path",
 "affine_transform","resample","reshape_image_to_4d_superpixel",
 "time_create","instrument_create","wavelength_create","level_create","source_create",
]
# --- round 3 expansion ---
ARGS.update({
 "rotated_sun_frame_create": {"base": C("sunpy.coordinates.HeliographicStonyhurst", obstime="2026-10-01T00:00:00"), "duration": Q(1, "day")},
 "differential_rotate": {"smap": SMAP, "time": "2026-10-01T06:00:00"},
 "map_sequence_create": {"_args": [SMAP, SMAP]},
 "composite_map_create": {"_args": [SMAP, SMAP]},
 "fido_search": {"_args": [C("sunpy.net.attrs.Time", "2026-10-01 00:00", "2026-10-01 00:10"), C("sunpy.net.attrs.Instrument", "AIA")]},
 "sample_create": {"value": Q(1, "minute")},
 "generic_map_reproject_to": {"target_wcs": C("astropy.wcs.WCS", HDR)},
})

# round 3 expansion (smoke-tested; dropped: differential_rotate, rotated_sun_frame_create)
SELECT += [
 "generic_map_reproject_to",
 "map_sequence_create",
 "composite_map_create",
 "fido_search",
 "sample_create",
]
