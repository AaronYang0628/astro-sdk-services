from dsl import *
loc = C("astropy.coordinates.EarthLocation.from_geodetic", Q(-155.47, "deg"), Q(19.82, "deg"), Q(4200, "m"))
obs = C("astroplan.Observer", location=loc, name="TestSite", timezone="UTC")
tgt = C("astroplan.FixedTarget", coord=SC(10.684, 41.269), name="M31")
t0 = C("astropy.time.Time", "2026-10-12 12:00:00")
tn = C("astropy.time.Time", "2026-10-13 06:00:00")
cons = [C("astroplan.AltitudeConstraint", min=Q(30, "deg")), C("astroplan.AtNightConstraint.twilight_astronomical")]
trange = C("astropy.time.Time", ["2026-10-12 08:00:00", "2026-10-12 16:00:00"])
ARGS = {
 "observer_create": {"location": loc, "name": "TestSite", "timezone": "UTC"},
 "observer_altaz": {"time": tn, "target": tgt},
 "observer_target_is_up": {"time": tn, "target": tgt},
 "observer_target_rise_time": {"time": t0, "target": tgt, "which": "next"},
 "observer_target_set_time": {"time": t0, "target": tgt, "which": "next"},
 "observer_target_meridian_transit_time": {"time": t0, "target": tgt, "which": "next"},
 "observer_sun_rise_time": {"time": t0, "which": "next"}, "observer_sun_set_time": {"time": t0, "which": "next"},
 "observer_twilight_evening_astronomical": {"time": t0, "which": "next"},
 "observer_moon_illumination": {"time": tn}, "observer_moon_altaz": {"time": tn}, "observer_is_night": {"time": tn},
 "observer_local_sidereal_time": {"time": tn}, "observer_parallactic_angle": {"time": tn, "target": tgt},
 "fixed_target_create": {"coord": SC(10.684, 41.269), "name": "M31"}, "fixed_target_from_name": {"query_name": "M31"},
 "is_observable": {"constraints": cons, "observer": obs, "targets": [tgt], "time_range": trange},
 "is_always_observable": {"constraints": cons, "observer": obs, "targets": [tgt], "time_range": trange},
 "observability_table": {"constraints": cons, "observer": obs, "targets": [tgt], "time_range": trange},
 "moon_illumination": {"time": tn}, "moon_phase_angle": {"time": tn},
 "time_grid_from_range": {"time_range": trange, "time_resolution": Q(1, "hour")},
 "eclipsing_system_next_primary_eclipse_time": {"time": t0},
 "altitude_constraint_create": {"min": Q(30, "deg")}, "airmass_constraint_create": {"max": 2.5},
 "at_night_constraint_create": {},
 "observer_tonight": {"time": t0},
}
SELF = {"astroplan.Observer": obs, "astroplan.periodic.EclipsingSystem": C("astroplan.EclipsingSystem", primary_eclipse_time=C("astropy.time.Time", "2026-10-01 00:00:00"), orbital_period=Q(2.5, "d")),
        "astroplan.EclipsingSystem": C("astroplan.EclipsingSystem", primary_eclipse_time=C("astropy.time.Time", "2026-10-01 00:00:00"), orbital_period=Q(2.5, "d"))}
SELECT = ["observer_create","observer_altaz","observer_target_is_up","observer_target_rise_time","observer_target_set_time","observer_sun_rise_time",
 "observer_sun_set_time","observer_twilight_evening_astronomical","observer_moon_illumination","observer_is_night","observer_local_sidereal_time",
 "observer_parallactic_angle","fixed_target_from_name","is_observable","is_always_observable","observability_table","moon_illumination",
 "moon_phase_angle","time_grid_from_range","eclipsing_system_next_primary_eclipse_time"]
