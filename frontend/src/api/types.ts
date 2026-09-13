export type PlanStatus =
  | 'draft'
  | 'pending_review'
  | 'revision_requested'
  | 'approved'
  | 'submitting'
  | 'submitted'
  | 'submission_failed'
  | 'unknown'

export type Provenance = 'source' | 'model_suggestion' | 'derived' | 'user_provided' | 'unresolved'

export interface EvidenceReference {
  evidence_segment_id: string
  section_type: string
  start_offset: number
  end_offset: number
  content_sha256: string
}

export interface FieldMetadata {
  provenance: Provenance
  evidence_references: EvidenceReference[]
}

export interface PlanStep {
  step_number: number
  action: string
}

export interface TestCaseContent {
  title: string
  objective: string
  preconditions: string[]
  steps: PlanStep[]
  test_data: string
  expected_result: string
  priority: string
  domain_key: string
  evidence_references: EvidenceReference[]
  provenance: Provenance
  open_questions: string[]
}

export interface RequirementContent {
  text: string
  evidence_references: EvidenceReference[]
  provenance: Provenance
}

export interface PlanDetailContent {
  domain_key: string
  domain_name: string
  domain_code: string
  owner_name: string
  owner_employee_id: string
  execution_start_date: string | null
  execution_end_date: string | null
  scope: string
  requirements: RequirementContent[]
  test_cases: TestCaseContent[]
  evidence_references: EvidenceReference[]
  unresolved_fields: string[]
  field_metadata: Record<string, FieldMetadata>
}

export interface TestPlanContent {
  plan_name: string
  project_name: string
  project_code: string
  requirement_ids: string[]
  test_type: string
  test_stage: string
  test_round: string
  priority: string
  test_version: string
  planned_start_date: string | null
  planned_end_date: string | null
  objective: string
  scope: string
  environment: string
  risks: string[]
  dependencies: string[]
  notes: string
  open_questions: string[]
  evidence_references: EvidenceReference[]
  details: PlanDetailContent[]
  field_metadata: Record<string, FieldMetadata>
}

export interface PlanSummary {
  id: string
  source_email_id: string
  current_version: number
  status: PlanStatus
  external_platform_id: string | null
  created_at: string
  updated_at: string
}

export interface PlanVersion {
  id: string
  test_plan_id: string
  version_number: number
  content: TestPlanContent
  content_sha256: string
  domain_catalog_version: string
  value_catalog_version: string
  prompt_version: string
  prompt_sha256: string
  created_at: string
}

export interface Plan extends PlanSummary {
  version: PlanVersion
}

export interface ImportResult {
  id: string
  original_filename: string
  subject: string | null
  parse_status: string
  extraction_status: string
  safe_error_summary: string | null
  deduplicated: boolean
  warnings: string[]
  test_plan_id: string | null
}

export interface ValidationIssue {
  id: string
  rule_id: string
  rule_version: string
  severity: 'blocking' | 'warning' | 'info'
  field_path: string | null
  message: string
  suggestion: string | null
}

export interface ValidationResult {
  id: string
  test_plan_id: string
  test_plan_version_id: string
  content_sha256: string
  rule_set_version: string
  status: 'passed' | 'failed'
  blocking_count: number
  warning_count: number
  finished_at: string
  issues: ValidationIssue[]
}

export interface ReviewRecord {
  id: string
  test_plan_id: string
  test_plan_version_id: string
  content_sha256: string
  operator_name: string
  operator_employee_id: string
  decision: 'approved' | 'revision_requested'
  comment: string | null
  acknowledged_warning_ids: string[]
  created_at: string
}

export interface PayloadPreview {
  id: string
  test_plan_id: string
  test_plan_version_id: string
  content_sha256: string
  mapping_profile_version: string
  payload: Record<string, unknown>
  canonical_json: string
  payload_sha256: string
  validation_status: 'valid'
  confirmation_token: string
  expires_at: string
  created_at: string
}

export interface Submission {
  id: string
  test_plan_id: string
  test_plan_version_id: string
  payload_preview_id: string
  mapping_profile_version: string
  payload_sha256: string
  submission_request_id: string
  idempotency_key: string
  status: 'submitting' | 'submitted' | 'submission_failed' | 'unknown'
  operator_name: string
  operator_employee_id: string
  confirmed_at: string
  external_request_id: string | null
  external_plan_id: string | null
  safe_response_summary: string | null
  finished_at: string | null
  created_at: string
}

export interface ApiErrorPayload {
  error?: {
    code?: string
    message?: string
    field?: string | null
    request_id?: string
  }
}
