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

// The statuses processor.py actually writes to records.status. Free-form model
// output is clamped onto this set by _canonical_status(), so keep the two in
// sync: the status filter options and the route's search enum are both built
// from this list, and a status missing here renders as an uncoloured raw
// string that no filter can match.
// __STATUSES_BLOCK_START__
export const statuses: {
  label: string
  value: string
  icon: typeof TriangleAlert
  severity: Severity
}[] = [
  { label: 'Valid', value: 'VALID', icon: CircleCheckBig, severity: 'good' as Severity },
  { label: 'Active', value: 'ACTIVE', icon: CircleCheckBig, severity: 'good' as Severity },
  { label: 'Expiring Soon', value: 'EXPIRING SOON', icon: Clock, severity: 'warning' as Severity },
  { label: 'Pending', value: 'PENDING', icon: Clock, severity: 'neutral' as Severity },
  { label: 'Pending Verification', value: 'PENDING VERIFICATION', icon: Clock, severity: 'warning' as Severity },
  { label: 'Pending Renewal Quote', value: 'PENDING RENEWAL QUOTE', icon: Clock, severity: 'warning' as Severity },
  { label: 'Expired', value: 'EXPIRED', icon: TriangleAlert, severity: 'critical' as Severity },
]
// __STATUSES_BLOCK_END__
