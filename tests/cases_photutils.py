from dsl import *
CUT = C("astropy.nddata.extract_array", IMG, {"__type__": "tuple", "items": [11, 11]}, {"__type__": "tuple", "items": [50, 50]})
POS = [[20, 30], [50, 50], [75, 25]]
ap = C("photutils.aperture.CircularAperture", POS, r=5.0)
ARGS = {
 "aperture_photometry": {"data": IMG, "apertures": ap},
 "aperture_stats": {"data": IMG, "aperture": ap},
 "find_peaks": {"data": IMG, "threshold": 300.0, "box_size": 5},
 "background2d": {"data": IMG, "box_size": 20},
 "detect_sources": {"data": IMG, "threshold": 200.0, "n_pixels": 5},
 "detect_threshold": {"data": IMG, "n_sigma": 3.0},
 "make_2dgaussian_kernel": {"fwhm": 3.0, "size": 5},
 "centroid_com": {"data": CUT}, "centroid_1dg": {"data": CUT}, "centroid_2dg": {"data": CUT}, "centroid_quadratic": {"data": CUT},
 "centroid_sources": {"data": IMG, "xpos": [20.0, 50.0], "ypos": [30.0, 50.0], "box_size": 11},
 "fit_fwhm": {"data": IMG, "xypos": [[50, 50]], "fit_shape": 7},
 "fit_2dgaussian": {"data": CUT},
 "data_properties": {"data": CUT}, "gini": {"data": CUT},
 "calc_total_error": {"data": IMG, "bkg_error": C("numpy.full", [100, 100], 5.0), "effective_gain": 1.0},
 "circular_footprint": {"radius": 3},
 "make_noise_image": {"shape": {"__type__": "tuple", "items": [10, 10]}, "distribution": "gaussian", "mean": 0.0, "stddev": 1.0, "seed": 1},
 "make_100gaussians_image": {},
 "circular_aperture_do_photometry": {"data": IMG},
 "circular_aperture_to_mask": {}, "scalar_background": {"data": IMG},
 "dao_star_finder": {"threshold": 100.0, "fwhm": 3.0}, "gaussian_prf_create": {}, "radial_profile_create": {"data": IMG, "xycen": {"__type__": "tuple", "items": [50.0, 50.0]}, "radii": [0, 2, 4, 6]},
}
SELF = {"photutils.aperture.CircularAperture": ap}
SELECT = ["aperture_photometry","aperture_stats","find_peaks","background2d","detect_sources","detect_threshold","make_2dgaussian_kernel",
 "centroid_com","centroid_1dg","centroid_2dg","centroid_quadratic","centroid_sources","fit_fwhm","fit_2dgaussian","data_properties","gini",
 "calc_total_error","circular_footprint","make_noise_image","circular_aperture_do_photometry"]
