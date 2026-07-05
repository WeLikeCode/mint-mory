{{/*
Expand the name of the chart.
*/}}
{{- define "mintmory.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Fully qualified app name (release-scoped).
*/}}
{{- define "mintmory.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Chart name and version label.
*/}}
{{- define "mintmory.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels.
*/}}
{{- define "mintmory.labels" -}}
helm.sh/chart: {{ include "mintmory.chart" . }}
{{ include "mintmory.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels.
*/}}
{{- define "mintmory.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mintmory.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Name of the PVC (existingClaim wins).
*/}}
{{- define "mintmory.pvcName" -}}
{{- if .Values.persistence.existingClaim -}}
{{- .Values.persistence.existingClaim -}}
{{- else -}}
{{- printf "%s-data" (include "mintmory.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Name of the basic-auth Secret (existingSecret wins).
*/}}
{{- define "mintmory.basicAuthSecretName" -}}
{{- if .Values.auth.basic.existingSecret -}}
{{- .Values.auth.basic.existingSecret -}}
{{- else -}}
{{- printf "%s-basic-auth" (include "mintmory.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Name of the oauth2-proxy workload/Service/Secret.
*/}}
{{- define "mintmory.oauth2ProxyName" -}}
{{- printf "%s-oauth2-proxy" (include "mintmory.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Image reference (tag falls back to the chart appVersion).
*/}}
{{- define "mintmory.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}
