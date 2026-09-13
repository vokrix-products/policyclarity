import { CircleCheckBig, TriangleAlert, Clock } from 'lucide-react'

export const labels = [
  {
    value: 'bug',
    label: 'Bug',
  },
  {
    value: 'feature',
    label: 'Feature',
  },
  {
    value: 'documentation',
    label: 'Documentation',
  },
]

// Severity tiers drive badge color. Every status maps to exactly one tier:
//   critical -> red (destructive)   e.g. expired, denied, failed
//   warning  -> amber (warning)     e.g. expiring soon, needs review
//   good     -> green (success)     e.g. valid, approved, done
//   neutral  -> gray (secondary)    e.g. pending, queued, n/a
export type Severity = 'critical' | 'warning' | 'good' | 'neutral'

export const severityToBadgeVariant: Record<Severity, 'destructive' | 'warning' | 'success' | 'secondary'> = {
  critical: 'destructive',
  warning: 'warning',
  good: 'success',
  neutral: 'secondary',
}

// PRODUCT_CUSTOMIZE: replace this list with the real statuses this product
// produces (must match exactly what the backend poller writes to
// records.status). Every status must declare a severity tier above. Default
// values below are generic placeholders only — do not ship as-is.
// __STATUSES_BLOCK_START__
export const statuses: {
  label: string
  value: string
  icon: typeof TriangleAlert
  severity: Severity
}[] = [
  { label: 'Compliant', value: 'compliant:good', icon: CircleCheckBig, severity: 'good' as Severity },
  { label: 'Missing', value: 'missing:critical', icon: TriangleAlert, severity: 'critical' as Severity },
  { label: 'Expired', value: 'expired:critical', icon: TriangleAlert, severity: 'critical' as Severity },
  { label: 'Expiring Soon', value: 'expiring_soon:warning', icon: Clock, severity: 'warning' as Severity },
  { label: 'Below Required Limit', value: 'below_required_limit:critical', icon: TriangleAlert, severity: 'critical' as Severity },
  { label: 'Additional Insured Missing', value: 'additional_insured_missing:critical', icon: TriangleAlert, severity: 'critical' as Severity },
  { label: 'Primary Noncontributory Missing', value: 'primary_noncontributory_missing:critical', icon: TriangleAlert, severity: 'critical' as Severity },
  { label: 'Waiver Subrogation Missing', value: 'waiver_subrogation_missing:warning', icon: Clock, severity: 'warning' as Severity },
  { label: 'Notice Cancellation Missing', value: 'notice_cancellation_missing:warning', icon: Clock, severity: 'warning' as Severity },
  { label: 'Sublimit Exclusion Gap', value: 'sublimit_exclusion_gap:critical', icon: TriangleAlert, severity: 'critical' as Severity },
  { label: 'Manuscript Endorsement Needs Review', value: 'manuscript_endorsement_needs_review:warning', icon: Clock, severity: 'warning' as Severity },
  { label: 'Policy Mismatch', value: 'policy_mismatch:critical', icon: TriangleAlert, severity: 'critical' as Severity },
  { label: 'Unable Verify', value: 'unable_verify:warning', icon: Clock, severity: 'warning' as Severity },
]
// __STATUSES_BLOCK_END__
