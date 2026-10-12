from dsl import *
ARGS = {
 "simbad_query_object": {"object_name": "M31"}, "simbad_query_objects": {"object_names": ["M31", "M42"]},
 "simbad_query_region": {"coordinates": SC(10.684, 41.269), "radius": Q(0.05, "deg")},
 "simbad_query_objectids": {"object_name": "M31"},
 "simbad_query_tap": {"query": "SELECT TOP 3 main_id, ra, dec FROM basic WHERE main_id = 'M  31'"},
 "simbad_list_votable_fields": {}, "simbad_get_votable_fields": {}, "simbad_list_tables": {},
 "simbad_get_field_description": {"field_name": "ra"}, "simbad_list_columns": {"_args": ["basic"]},
 "vizier_find_catalogs": {"keywords": "Gaia"}, "vizier_query_object": {"_args": ["M31"], "catalog": "I/239/hip_main"},
 "vizier_query_region": {"_args": [SC(10.684, 41.269)], "radius": Q(0.05, "deg"), "catalog": "I/239/hip_main"},
 "ned_query_object": {"object_name": "M31"}, "ned_query_region": {"coordinates": SC(10.684, 41.269), "radius": Q(0.05, "deg")},
 "gaia_cone_search": {"coordinate": SC(10.684, 41.269), "radius": Q(0.02, "deg")},
 "gaia_launch_job": {"query": "SELECT TOP 3 source_id, ra, dec FROM gaiadr3.gaia_source"},
 "mpc_get_observatory_location": {"code": "500"} , "mpc_get_observatory_codes": {},
 "irsa_dust_get_extinction_table": {"coordinate": SC(10.684, 41.269)},
 "heasarc_list_catalogs": {"keywords": "swift"}, "jpl_spec_get_species_table": {},
 "sdss_query_region": {"coordinates": SC(10.684, 41.269), "radius": Q(0.02, "deg")},
 "nasa_exoplanet_archive_query_object": {"object_name": "TRAPPIST-1 b"},
 "irsa_list_catalogs": {}, "ned_get_table": {"object_name": "M31", "table": "positions"},
}
SELF = {}
SELECT = ['simbad_query_object', 'simbad_query_objects', 'simbad_query_region', 'simbad_query_objectids', 'simbad_query_tap', 'simbad_list_votable_fields', 'simbad_get_votable_fields', 'simbad_list_tables', 'simbad_get_field_description', 'simbad_list_columns', 'vizier_find_catalogs', 'vizier_query_object', 'vizier_query_region', 'gaia_cone_search', 'gaia_launch_job', 'mpc_get_observatory_location', 'irsa_dust_get_extinction_table', 'heasarc_list_catalogs', 'jpl_spec_get_species_table', 'nasa_exoplanet_archive_query_object']
