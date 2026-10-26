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
{{- $roots := .Values.euclid.inputRoots | default "" }}
{{- if and (not $roots) (include "astro.projectStorageOn" .) }}{{ $roots = .Values.euclid.projectStorage.mountPath }}{{ end }}
{{- with $roots }}
- {name: EUCLID_INPUT_ROOTS, value: {{ . | quote }}}
{{- end }}
{{- end }}
{{/* "true" when a project-storage source (existingClaim / hostPath / nfs) is configured */}}
{{- define "astro.projectStorageOn" -}}
{{- $ps := .Values.euclid.projectStorage | default dict }}
{{- if or $ps.existingClaim $ps.hostPath (and $ps.nfs $ps.nfs.server) }}true{{ end }}
{{- end }}
{{- define "astro.euclidMounts" -}}
- {name: euclid-data, mountPath: /data/euclid}
{{- if include "astro.projectStorageOn" . }}
{{- $ps := .Values.euclid.projectStorage }}
- name: project-storage
  mountPath: {{ $ps.mountPath | default "/home/scientist" | quote }}
  readOnly: {{ if eq (toString $ps.readOnly) "false" }}false{{ else }}true{{ end }}
  {{- with $ps.subPath }}
  subPath: {{ . | quote }}
  {{- end }}
{{- end }}
{{- end }}
{{- define "astro.euclidVolume" -}}
- name: euclid-data
{{- if .Values.euclid.storage.existingClaim }}
  persistentVolumeClaim: {claimName: {{ .Values.euclid.storage.existingClaim }}}
{{- else }}
  emptyDir: {sizeLimit: {{ .Values.euclid.storage.sizeLimit }}}
{{- end }}
{{- if include "astro.projectStorageOn" . }}
{{- $ps := .Values.euclid.projectStorage }}
- name: project-storage
{{- if $ps.existingClaim }}
  persistentVolumeClaim: {claimName: {{ $ps.existingClaim | quote }}, readOnly: true}
{{- else if $ps.hostPath }}
  hostPath: {path: {{ $ps.hostPath | quote }}, type: Directory}
{{- else }}
  nfs: {server: {{ $ps.nfs.server | quote }}, path: {{ $ps.nfs.path | default "/" | quote }}, readOnly: true}
{{- end }}
{{- end }}
{{- end }}
