import { type ColumnDef } from '@tanstack/react-table'
import { ExternalLink } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { DataTableColumnHeader } from '@/components/data-table'
import { supabase } from '@/lib/supabase'
import { statuses, severityToBadgeVariant } from '../data/data'
import { type Task } from '../data/schema'
import { DataTableRowActions } from './data-table-row-actions'

async function openSourceFile(path: string) {
  const { data, error } = await supabase.storage
    .from('uploads')
    .createSignedUrl(path, 60 * 60) // 1 hour
  if (error || !data?.signedUrl) return
  window.open(data.signedUrl, '_blank')
}

function formatDueDate(iso: string | null | undefined): string | null {
  if (!iso) return null
  const date = new Date(iso)
  const now = new Date()
  const diffDays = Math.ceil(
    (date.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)
  )
  const label = date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
  if (diffDays < 0) return `${label} (overdue)`
  if (diffDays <= 30) return `${label} (${diffDays}d)`
  return label
}

export const tasksColumns: ColumnDef<Task>[] = [
  {
    id: 'select',
    header: ({ table }) => (
      <Checkbox
        checked={
          table.getIsAllPageRowsSelected() ||
          (table.getIsSomePageRowsSelected() && 'indeterminate')
        }
        onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
        aria-label='Select all'
        className='translate-y-0.5'
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        checked={row.getIsSelected()}
        onCheckedChange={(value) => row.toggleSelected(!!value)}
        aria-label='Select row'
        className='translate-y-0.5'
      />
    ),
    enableSorting: false,
    enableHiding: false,
  },
  {
    accessorKey: 'id',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='ID' />
    ),
    cell: ({ row }) => <div className='w-20'>{row.getValue('id')}</div>,
    enableSorting: false,
    enableHiding: true,
  },
  {
    accessorKey: 'title',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Name' />
    ),
    meta: {
      className: 'ps-1 max-w-0 w-2/3',
      tdClassName: 'ps-4',
    },
    cell: ({ row }) => {
      return (
        // min-w-0 is required: without it this flex item keeps the default
        // min-width:auto, so the truncate span below can never shrink below
        // its content width and long names overflow the cell.
        <div className='flex min-w-0 items-center space-x-2'>
          <span className='truncate font-medium'>{row.getValue('title')}</span>
        </div>
      )
    },
  },
  {
    accessorKey: 'status',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Status' />
    ),
    // Pin the column. Long free-form statuses (legacy rows that are not in the
    // closed status set) would otherwise let the column grow without limit.
    meta: { className: 'ps-1 w-40 max-w-40', tdClassName: 'ps-4' },
    cell: ({ row }) => {
      const statusValue = row.getValue('status') as string
      const statusDef = statuses.find((s) => s.value === statusValue)
      const severity = statusDef?.severity ?? 'neutral'
      const badgeVariant = severityToBadgeVariant[severity]
      const Icon = statusDef?.icon
      const label = statusDef?.label ?? statusValue
      return (
        <div className='flex min-w-0 max-w-full items-center gap-2'>
          {/*
            Badge base classes are w-fit + shrink-0 (+ overflow-hidden), which
            means it sizes to its own text and refuses to shrink inside this
            flex parent - so the badge used to escape the cell and paint over
            the next column. min-w-0/max-w-full/shrink override that, and the
            label is truncated inside with the full value kept in title.
          */}
          <Badge
            variant={badgeVariant}
            className='min-w-0 max-w-full shrink items-center gap-1'
            title={label}
          >
            {Icon && <Icon className='size-3 shrink-0' />}
            <span className='min-w-0 truncate'>{label}</span>
          </Badge>
        </div>
      )
    },
    filterFn: (row, id, value) => value.includes(row.getValue(id)),
  },
  {
    // PRODUCT_CUSTOMIZE: show due_date column only for products where records
    // have expiration/renewal/deadline dates (COI, credentialing, permits,
    // insurance). Remove this column definition for products without dates.
    accessorKey: 'due_date',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title='Due / Expires' />
    ),
    meta: { className: 'ps-1 whitespace-nowrap', tdClassName: 'ps-4' },
    cell: ({ row }) => {
      const val = row.getValue('due_date') as string | null | undefined
      const formatted = formatDueDate(val)
      if (!formatted) return <span className='text-muted-foreground'>—</span>
      const isOverdue = formatted.includes('overdue')
      const isSoon =
        !isOverdue && formatted.includes('d)') && parseInt(formatted.split('(')[1]) <= 30
      return (
        <span
          className={
            isOverdue
              ? 'text-destructive font-medium'
              : isSoon
                ? 'text-warning font-medium'
                : 'text-foreground'
          }
        >
          {formatted}
        </span>
      )
    },
  },
  {
    // PRODUCT_CUSTOMIZE: source document link. Keep for any product that
    // extracts data from uploaded documents (PDFs, CSVs). The poller must
    // write the original upload path to records.source_file_path.
    id: 'source',
    header: () => <span className='text-xs text-muted-foreground'>Source</span>,
    cell: ({ row }) => {
      const path = row.original.source_file_path
      if (!path) return null
      return (
        <Button
          variant='ghost'
          size='sm'
          className='h-7 px-2'
          onClick={() => openSourceFile(path)}
        >
          <ExternalLink className='size-3.5 mr-1' />
          View
        </Button>
      )
    },
    enableSorting: false,
    enableHiding: true,
  },

  {
    id: 'actions',
    cell: ({ row }) => <DataTableRowActions row={row} />,
  },
]
