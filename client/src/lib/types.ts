// Shapes of API responses (see api/app/api/*). Only the fields the client reads.
export interface Me {
  id: number;
  first_name: string;
  username: string | null;
  tz: string;
  is_admin: boolean;
  is_curator: boolean;
  curator_requests: number;
  settings: {
    band: "A" | "B" | "C";
    band_pending: boolean;
    python_level: "none" | "little" | "yes";
    daily_time: string;
    notifications: Record<string, boolean>;
    vacation_days: string[];
    easy_days: string[];
    challenge_enabled: boolean;
    run_code_on_server: boolean;
    show_timer: boolean;
    cosmetics: string[];
    onboarding_step: number;
    onboarding_done: boolean;
    placement_done: boolean;
    consent: boolean;
  };
  wallet: { balance: number; xp: number; rank: string; next_rank_xp: number | null; exam_tickets: number };
  streak: { current: number; best: number; freezes: number };
  band_suggestion: "A" | "B" | "C" | null;
  fipi: { version: string; approved: boolean; banner: string | null };
  delete_requested_at: string | null;
}

export interface AssetMeta {
  name: string;
  mime: string;
  kind: string;
  size: number;
  inline: boolean;
  deferred: boolean;
  content?: string;
}

export interface InstanceView {
  id: number;
  task_no: number;
  subtype: string;
  difficulty: number;
  context: string;
  slot: string;
  mandatory: boolean;
  statement_md: string;
  assets: AssetMeta[];
  answer_kind: string;
  checker_options: Record<string, unknown>;
  method_card_id: string;
  target_seconds: number;
  requires_code: boolean;
  flags: string[];
  state: string;
  attempts_count: number;
  hints_used: number;
  revealed: boolean;
  expires_at: string | null;
  draft: { answer?: string; code?: string; notes?: string };
  exam_id: number | null;
  reward?: number;
  hint_price?: number | null;
  hints_left?: number;
  hints?: string[];
  reveal_price?: number | null;
  free_reveal_available?: boolean;
  checklist?: string[];
  code_rule?: string;
  solution?: Solution;
}

export interface Solution {
  answer: string;
  steps: string[];
  reference_code: string | null;
  method_card_id: string;
}

export interface AnswerResult {
  status: "correct" | "wrong" | "format_error" | "method_check";
  message?: string;
  question?: string;
  options?: string[];
  counted: boolean;
  attempt_no?: number;
  attempts_left?: number;
  coins?: number;
  capped?: number;
  xp?: number;
  rank?: string;
  rank_up?: boolean;
  verify_status?: string;
  verdict_text?: string;
  method_note?: string;
  ask_reason?: boolean;
  threshold_met?: boolean;
  milestones?: number[];
  cap_reached?: boolean;
  confidence?: { task_no: number; before: number; after: number };
  context_result?: {
    placement?: { answered?: number; total?: number; next_instance_id?: number; finished?: boolean; floors?: number[]; challenge?: boolean; correct?: number };
    trial_id?: number;
    kind?: string;
    correct?: number;
    total?: number;
    finished?: boolean;
    passed?: boolean;
  };
}

export interface TodayItem {
  slot: string;
  task_no: number;
  subtype: string;
  difficulty: number;
  mandatory: boolean;
  target_seconds: number;
  instance_id: number;
  flags: string[];
  title: string;
  state: string;
  minutes: number;
  reward: number;
}

export interface Today {
  day: string;
  streak: { current: number; best: number; freezes: number };
  wallet: { balance: number; xp: number; rank: string; next_rank_xp: number | null };
  progress: { earned: number; threshold: number; cap: number; threshold_met: boolean; cap_reached: boolean; easy_day: boolean };
  items: TodayItem[];
  free_practice: boolean;
  free_reveal_available: boolean;
  reveal_candidate: number | null;
  all_done: boolean;
  next_open_at: string;
  show_timer: boolean;
}

export interface FloorView {
  number: number;
  title: string;
  python: string;
  state: "locked" | "unlocked" | "boss_passed";
  required: boolean;
  price: number;
  mastered: number;
  total: number;
  tasks: { task_no: number; title: string; confidence: number; colour: string }[];
  boss_passed: boolean;
}

export interface PathView {
  band: string;
  current: number;
  extern_available: boolean;
  floors: FloorView[];
}

export interface Trial {
  trial_id: number;
  kind: "extern" | "boss";
  floor: number;
  instances: InstanceView[];
}

export interface ConfidenceItem {
  task_no: number;
  title: string;
  points: number;
  value: number;
  colour: string;
  trend: "up" | "down" | "flat";
  attempts: number;
  arbiter: boolean;
  arbiter_note?: string;
}

export interface ConfidenceView {
  forecast: { primary: number; test: number; margin: number; from_exam: boolean };
  band: { code: string; title: string; range: [number, number] };
  focus: number[];
  tasks: ConfidenceItem[];
}

export interface ProgressDay {
  date: string;
  coins: number;
  tasks: number;
  threshold_met: boolean;
  easy: boolean;
  vacation: boolean;
  today: boolean;
}

export interface ProgressView {
  range: string;
  threshold: number;
  cap: number;
  days: ProgressDay[];
  milestones: number[];
  totals: { streak: number; best_streak: number; solved: number; hours: number; active_days: number; rank: string; xp: number; next_rank_xp: number | null };
  week: { day: string; avg_tasks: number }[];
}

export interface ExamSheetItem {
  position: number;
  task_no: number;
  answered: boolean;
  answer: string | null;
  time_spent_s: number;
  instance: InstanceView;
  correct?: boolean | null;
  points?: number;
}

export interface ExamResult {
  primary: number | null;
  test: number | null;
  per_position: { position: number; task_no: number; points: number; correct: boolean | null; time_spent_s: number; instance_id: number }[];
  lost_most: number[];
  history: { id: number; finished_at: string; primary: number }[];
  reveals_free: boolean;
}

export interface ExamView {
  id: number;
  kind: "full" | "half" | "block";
  training: boolean;
  started_at: string;
  deadline_at: string | null;
  seconds_left: number;
  paused: boolean;
  finished: boolean;
  sheet: ExamSheetItem[];
  result: ExamResult | null;
}

export interface CuratorLinkView {
  id: number;
  name: string;
  username: string | null;
  role: "parent" | "tutor";
  access: "fact" | "progress" | "full";
  status: "pending" | "active";
}

export interface StudentRow {
  student_id: number;
  name: string;
  link_id: number;
  access: string;
  role: string;
  days_idle: number;
  risk: number;
  streak?: { current: number; best: number } | number;
  threshold_today?: boolean;
  rank?: string;
}
