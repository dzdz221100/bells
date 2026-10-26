export type Wedding = {
  id: number
  couple_names: string
  date: string
  city: string
  country: string
  timezone: string
  currency: string
}

export type GuestSummary = {
  id: number
  name: string
  language: string
  party_size: number
}

export type Hotel = {
  id: number
  name: string
  address: string | null
  block_code: string | null
  nightly_rate: number | null
  book_by_date: string | null
  url: string | null
  distance_km: number | null
}

export type ShuttleRun = {
  id: number
  direction: 'arrival' | 'departure'
  depart_at: string
  from_loc: string
  to_loc: string
  capacity: number
  seats_taken: number
}

export type RegistryItem = {
  id: number
  item: string
  url: string | null
  image_url: string | null
  price: number | null
  available: boolean
  claimed_by_you: boolean
}

export type Dashboard = {
  guest: {
    id: number
    name: string
    language: string
    party_size: number
    rsvp_status: 'pending' | 'attending' | 'declined'
    rsvp_at: string | null
    dietary: string | null
    plus_one_allowed: boolean
    plus_one_name: string | null
    plus_one_dietary: string | null
    hotel_booked: boolean
    arrival_flight: string | null
    arrival_at: string | null
    departure_at: string | null
  }
  hotel: Hotel | null
  pickup: {
    run: ShuttleRun | null
    minutes_after_landing: number | null
    be_at_pickup_by: string | null
    text: string
    drive_minutes: number
  }
  registry: {
    total: number
    available: number
    yours: { id: number; item: string; price: number | null }[]
    items: RegistryItem[]
  }
}

export type ToolEvent = {
  seq: number
  agent: string
  tool: string
  args: Record<string, unknown>
  status: string
  detail: string
  ms: number
}

export type Tokens = {
  requests: number
  tool_calls: number
  input_tokens: number
  cached_tokens: number
  cache_write_tokens: number
  output_tokens: number
  total_tokens: number
}

export type ChatReply = {
  answer: string
  escalated: boolean
  agents_called: string[]
  tools_called: string[]
  events: ToolEvent[]
  tokens: Tokens
  cost_usd: number | null
  cost_basis: string
  model: string
  elapsed_ms: number
}

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'error'
  content: string
  reply?: ChatReply
}

/* ---------------------------------------------------------------- host */

export type Escalation = {
  id: number
  wedding_id: number
  guest_id: number | null
  question: string
  status: 'open' | 'answered' | 'dismissed'
  draft_answer: string | null
  host_answer: string | null
  created_at: string
  resolved_at: string | null
  guest_name: string | null
  guest_language: string | null
}

export type Impact = {
  turns: number
  answered_automatically: number
  escalated: number
  escalation_rate: number | null
  inbox: { open: number; answered: number; dismissed: number }
  facts_total: number
  facts_from_host_console: number
  guests_total: number
  default_minutes_per_question: number
}

export type Spend = {
  turns: number
  guests_seen: number
  guests_total: number
  model: string
  tokens: {
    input: number
    cached: number
    uncached: number
    cache_write: number
    output: number
    total: number
  }
  cache_hit_rate: number | null
  cost_usd: number | null
  cost_basis: string
  per_guest: { tokens: number | null; cost_usd: number | null }
  projection: { guests: number; tokens: number | null; cost_usd: number | null }
}

export type RunMember = {
  guest_id: number
  name: string
  party_size: number
  arrival_flight: string | null
  arrival_at: string
  wait_minutes: number
}

export type ScheduleRun = {
  id: number
  depart_at: string
  from_loc: string
  to_loc: string
  capacity: number
  seats_taken: number
  members: RunMember[]
  max_wait_minutes: number
  first_landing: string | null
  last_landing: string | null
}

export type ScheduleSide = {
  label: string
  runs: number
  total_wait_person_minutes: number
  max_wait_minutes: number
  driver_hours: number
  transfer_cost_eur: number
}

export type ScheduleReport = {
  wedding_id: number
  capacity: number
  runs: ScheduleRun[]
  bookings: number
  seats: number
  unscheduled: string[]
  baseline: ScheduleSide
  solved: ScheduleSide
  savings: {
    runs: number
    runs_pct: number
    driver_hours: number
    transfer_cost_eur: number
    extra_wait_person_minutes: number
  }
  assumptions: {
    cost_per_transfer_eur: number
    minutes_per_round_trip: number
    buffer_minutes: number
    max_wait_minutes: number
  }
}

export type ApproveResult = {
  ok: boolean
  escalation_id: number
  fact_id: number
  topic: string
  is_public: boolean
  message: string
}

export type MyRegistry = {
  total: number
  available: number
  taken_by_others: number
  items: RegistryItem[]
  yours: RegistryItem[]
}

export type Overview = {
  invited: number
  rsvp: {
    attending: number
    declined: number
    pending: number
    response_rate: number | null
  }
  seats: { attending: number; invited: number; pending: number }
  dietary: { need: string; people: number }[]
  dietary_people: number
  languages: { code: string; guests: number }[]
  beds: { hotel: string; people: number }[]
  plus_ones: { invited: number; named: number; unnamed: number }
  travel: { with_flights: number; on_a_shuttle: number; no_shuttle_yet: number }
  registry: { total: number; available: number; chosen: number }
}

/* ------------------------------------------------- host concierge ---- */

export type HostProposal = {
  id: string
  kind: string
  summary: string
  detail: Record<string, unknown>
  before: Record<string, any>
  after: Record<string, any>
  created_at?: string
}

export type MessageDraft = {
  id: string
  guest_id: number
  name: string
  email: string
  language: string
  segment: string
  intent: string
  situation: string
  message: string
  status: 'draft' | 'approved' | 'sent' | 'skipped'
  edited?: boolean
}

export type DraftBundle = {
  total: number
  awaiting: number
  segments: { segment: string; intent: string; drafts: MessageDraft[] }[]
}

export type HostReply = ChatReply & {
  proposals: HostProposal[]
  committed: string[]
  drafts: MessageDraft[]
}
