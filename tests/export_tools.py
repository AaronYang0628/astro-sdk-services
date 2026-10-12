import pandas as pd, re, json, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/workspace/astro_services")
from common.engine import resolve_target
FIX = {'photutils_aperture_photometry':'photutils.aperture.aperture_photometry','photutils_aperture_stats':'photutils.aperture.ApertureStats',
'photutils_dao_star_finder':'photutils.detection.DAOStarFinder','photutils_iraf_star_finder':'photutils.detection.IRAFStarFinder',
'photutils_find_peaks':'photutils.detection.find_peaks','photutils_background2d':'photutils.background.Background2D',
'photutils_scalar_background':'photutils.background.BackgroundBase','photutils_detect_sources':'photutils.segmentation.detect_sources',
'photutils_deblend_sources':'photutils.segmentation.deblend_sources','photutils_psf_photometry':'photutils.psf.PSFPhotometry',
'photutils_iterative_psf_photometry':'photutils.psf.IterativePSFPhotometry','photutils_build_epsf':'photutils.psf.EPSFBuilder'}
d = pd.read_excel('/workspace/2178个天文工具.xlsx')
for lib in ['astropy','astroquery','photutils','astroplan','sunpy']:
    out = []; bad = []
    for _, r in d[d['库']==lib].iterrows():
        m = re.search(r'底层调用\s*([\w\.]+)', r['功能描述'])
        tgt = m.group(1).rstrip('.') if m else None
        tgt = FIX.get(r['工具名'], tgt)
        params = []
        for line in str(r['参数列表']).split('\n'):
            mm = re.match(r'(\w+)\[(.*?)\] (必填|可选): ?(.*)', line)
            if mm: params.append({"name": mm[1], "type": mm[2], "required": mm[3]=="必填", "desc": mm[4]})
        ok = False
        if tgt:
            try: resolve_target(tgt); ok = True
            except Exception as e: pass
        if not ok: bad.append((r['工具名'], tgt)); continue
        out.append({"name": r['工具名'], "target": tgt, "desc": r['功能描述'], "params": params,
                    "domain": r['类别'], "cn": r['中文名'], "orig_params": r['参数列表']})
    json.dump(out, open(f'data/{lib}_tools_all.json','w'), ensure_ascii=False, indent=1)
    print(lib, len(out), 'unresolved', bad)
