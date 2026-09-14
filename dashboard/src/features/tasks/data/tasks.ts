import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { supabase, PRODUCT_ID } from '@/lib/supabase'
import { useAuthStore } from '@/stores/auth-store'
import { type Task } from './schema'

/**
 * records.details is jsonb and holds two shapes in the wild:
 *   - an object, written by the poller and by manual edits
 *   - a plain human-readable sentence, written by older processor.py versions
 *
 * taskSchema declares it as a record, so a string fails validation and the
 * row throws during render (the policies tab 500s). Normalise it here, at the
 * fetch boundary, so every consumer downstream sees exactly one shape.
 */
function normalizeDetails(value: unknown): Record<string, unknown> | null {
  if (value === null || value === undefined) return null

  if (typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }

  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return null
    try {
      const parsed: unknown = JSON.parse(trimmed)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>
      }
    } catch {
      // Not JSON - legacy prose. Wrapped as a summary below.
    }
    return { summary: trimmed }
  }

  return { summary: String(value) }
}

async function writeAudit(action: string, entity: string, entityId: string, userId: string) {
  try {
    await supabase.from('audit_log').insert({
      product_id: PRODUCT_ID,
      customer_id: userId,
      action,
      entity,
      entity_id: entityId,
    })
  } catch (e) {
    void e
  }
}

async function fetchTasks(): Promise<Task[]> {
  const { data, error } = await supabase
    .from('records')
    .select('id, title, status, label, priority, details, source_file_path, due_date')
    .eq('product_id', PRODUCT_ID)
    .order('created_at', { ascending: false })

  if (error) throw error

  return (data ?? []).map((row) => ({
    id: String(row.id),
    title: row.title,
    status: row.status,
    label: row.label ?? '',
    priority: row.priority ?? '',
    details: normalizeDetails(row.details),
    source_file_path: row.source_file_path ?? null,
    due_date: row.due_date ?? null,
  }))
}

export function useTasks() {
  return useQuery({
    queryKey: ['tasks', PRODUCT_ID],
    queryFn: fetchTasks,
  })
}

async function deleteTask(id: string): Promise<void> {
  const { error } = await supabase
    .from('records')
    .delete()
    .eq('id', id)
    .eq('product_id', PRODUCT_ID)

  if (error) throw error
}

export function useDeleteTask() {
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.auth.user)
  return useMutation({
    mutationFn: deleteTask,
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['tasks', PRODUCT_ID] })
      if (user?.id) void writeAudit('record.deleted', 'record', id, user.id)
    },
  })
}

async function deleteTasks(ids: string[]): Promise<void> {
  const { error } = await supabase
    .from('records')
    .delete()
    .in('id', ids)
    .eq('product_id', PRODUCT_ID)

  if (error) throw error
}

export function useDeleteTasks() {
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.auth.user)
  return useMutation({
    mutationFn: deleteTasks,
    onSuccess: (_, ids) => {
      queryClient.invalidateQueries({ queryKey: ['tasks', PRODUCT_ID] })
      if (user?.id) {
        ids.forEach(id => void writeAudit('record.deleted', 'record', id, user.id))
      }
    },
  })
}

type UpsertTaskInput = Partial<Task> & { title: string; status: string }

async function upsertTask(
  task: UpsertTaskInput,
  customerId: string
): Promise<void> {
  const payload: Record<string, unknown> = {
    title: task.title,
    status: task.status,
    label: task.label || null,
    priority: task.priority || null,
    product_id: PRODUCT_ID,
    customer_id: customerId,
  }
  if (task.id) payload.id = task.id

  const { error } = await supabase.from('records').upsert(payload)

  if (error) throw error
}

export function useUpsertTask() {
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.auth.user)
  return useMutation({
    mutationFn: (task: UpsertTaskInput) => {
      if (!user) throw new Error('Not authenticated')
      return upsertTask(task, user.id)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks', PRODUCT_ID] })
    },
  })
}

type ImportTaskRow = {
  title: string
  status: string
  label?: string
  priority?: string
}

async function importTasks(
  rows: ImportTaskRow[],
  customerId: string
): Promise<number> {
  const payload = rows.map((row) => ({
    title: row.title,
    status: row.status,
    label: row.label || null,
    priority: row.priority || null,
    product_id: PRODUCT_ID,
    customer_id: customerId,
  }))

  const { error } = await supabase.from('records').insert(payload)

  if (error) throw error
  return payload.length
}

export function useImportTasks() {
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.auth.user)
  return useMutation({
    mutationFn: (rows: ImportTaskRow[]) => {
      if (!user) throw new Error('Not authenticated')
      return importTasks(rows, user.id)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks', PRODUCT_ID] })
    },
  })
}
