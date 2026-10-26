{{/* euclid env + volume mount for a container */}}
{{- define "astro.euclidEnv" -}}
- {name: EUCLID_CACHE_DIR, value: {{ .Values.euclid.cacheDir | quote }}}
- {name: EUCLID_OUTPUT_DIR, value: {{ .Values.euclid.outputDir | quote }}}
{{- with .Values.euclid.merRoot }}
- {name: EUCLID_MER_ROOT, value: {{ . | quote }}}
{{- end }}
{{- with .Values.euclid.tileIndex }}
- {name: EUCLID_TILE_INDEX, value: {{ . | quote }}}
{{- end }}
{{- end }}
{{- define "astro.euclidVolume" -}}
- name: euclid-data
{{- if .Values.euclid.storage.existingClaim }}
  persistentVolumeClaim: {claimName: {{ .Values.euclid.storage.existingClaim }}}
{{- else }}
  emptyDir: {sizeLimit: {{ .Values.euclid.storage.sizeLimit }}}
{{- end }}
{{- end }}
