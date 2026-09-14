import { z } from 'zod'

// We're keeping a simple non-relational schema here.
// IRL, you will have a schema for your data models.
export const taskSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: z.string(),
  label: z.string(),
  priority: z.string(),
  // records.details is jsonb and holds two shapes: the structured object the
  // poller writes, and legacy free-form prose written by earlier processor
  // versions. Accept both; tasks.ts normalises to an object at the fetch
  // boundary so every consumer below it sees exactly one shape.
  details: z
    .union([z.record(z.string(), z.unknown()), z.string()])
    .nullable()
    .optional(),
  // Path in the 'uploads' bucket to the original document this record
  // came from, for verifying extraction against the source.
  source_file_path: z.string().nullable().optional(),
  // Optional deadline/expiration/renewal date, if this product has one.
  due_date: z.string().nullable().optional(),
})

export type Task = z.infer<typeof taskSchema>
