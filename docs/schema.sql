BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE activityformat AS ENUM ('workshop', 'seminar', 'conference');

CREATE TYPE assignmentstatus AS ENUM ('invited', 'reminded', 'accepted', 'declined', 'replaced_no_response', 'report_received', 'withdrawn');

CREATE TYPE authorrole AS ENUM ('sole', 'main', 'co_author');

CREATE TYPE authprovider AS ENUM ('local', 'oidc');

CREATE TYPE bookitemtype AS ENUM ('knowledge_contribution', 'specialized', 'textbook', 'heritage', 'chapter');

CREATE TYPE casestatus AS ENUM ('draft', 'submitted', 'not_eligible', 'under_evaluation', 'hod_review', 'dean_review', 'returned_for_revision', 'referee_selection', 'awaiting_referee_reports', 'referee_results_recorded', 'withdrawn');

CREATE TYPE component AS ENUM ('eligibility', 'research', 'teaching', 'service', 'report_builder', 'chancellor_office');

CREATE TYPE confidence AS ENUM ('high', 'medium', 'low');

CREATE TYPE courselevel AS ENUM ('undergraduate', 'graduate');

CREATE TYPE criterionarea AS ENUM ('eligibility', 'research', 'teaching', 'service', 'referees', 'general');

CREATE TYPE deanrating AS ENUM ('excellent', 'very_good', 'good');

CREATE TYPE decisionbasis AS ENUM ('rule', 'llm', 'mixed');

CREATE TYPE degreelevel AS ENUM ('bachelor', 'master', 'phd', 'other_doctorate');

CREATE TYPE deliverymode AS ENUM ('face_to_face', 'blended', 'online');

CREATE TYPE deliverystatus AS ENUM ('queued', 'sent', 'failed');

CREATE TYPE developmentdepth AS ENUM ('deep', 'mild');

CREATE TYPE documentkind AS ENUM ('evidence', 'signed_form', 'generated_form', 'screenshot', 'photo', 'cv', 'referee_report');

CREATE TYPE flagseverity AS ENUM ('info', 'warning', 'needs_human');

CREATE TYPE gate AS ENUM ('hod', 'dean');

CREATE TYPE gateoutcome AS ENUM ('approve', 'return_for_revision');

CREATE TYPE graduatedegree AS ENUM ('msc', 'phd');

CREATE TYPE investigatorrole AS ENUM ('pi', 'ci');

CREATE TYPE journalclass AS ENUM ('class_a', 'class_b', 'not_counted');

CREATE TYPE language AS ENUM ('english', 'arabic', 'other');

CREATE TYPE lookupsource AS ENUM ('doi', 'title_search', 'profile_import', 'manual');

CREATE TYPE mainauthorbasis AS ENUM ('first_author', 'corresponding_author', 'supervision_rule', 'other');

CREATE TYPE messagekind AS ENUM ('invitation', 'reminder', 'replacement_notice', 'thank_you');

CREATE TYPE orglevel AS ENUM ('department', 'college', 'university');

CREATE TYPE patentstatus AS ENUM ('filed', 'granted');

CREATE TYPE profilesource AS ENUM ('scopus', 'openalex');

CREATE TYPE projectstatus AS ENUM ('ongoing', 'completed');

CREATE TYPE promotiontrack AS ENUM ('to_associate', 'to_full');

CREATE TYPE publicationstatus AS ENUM ('published', 'accepted');

CREATE TYPE rank AS ENUM ('lecturer', 'assistant_professor', 'associate_professor', 'professor');

CREATE TYPE role_name AS ENUM ('applicant', 'hod', 'dean', 'chancellor', 'admin');

CREATE TYPE rubriccode AS ENUM ('teaching', 'service');

CREATE TYPE runstatus AS ENUM ('running', 'succeeded', 'failed');

CREATE TYPE semester AS ENUM ('fall', 'spring', 'summer');

CREATE TYPE supervisionrole AS ENUM ('main', 'associate');

CREATE TYPE supervisionstatus AS ENUM ('in_progress', 'graduated');

CREATE TYPE teachingrole AS ENUM ('instructor', 'instructor_coordinator');

CREATE TYPE verdict AS ENUM ('pass', 'fail', 'needs_human', 'incomplete');

CREATE TYPE workshoprole AS ENUM ('organiser', 'lecturer', 'organiser_and_lecturer');

CREATE TABLE college (
    id BIGSERIAL NOT NULL, 
    code VARCHAR(20) NOT NULL, 
    name_en VARCHAR(200) NOT NULL, 
    name_ar VARCHAR(200), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_college PRIMARY KEY (id), 
    CONSTRAINT uq_college_code UNIQUE (code)
);

CREATE TABLE journal (
    id BIGSERIAL NOT NULL, 
    title VARCHAR(400) NOT NULL, 
    issn VARCHAR(9), 
    eissn VARCHAR(9), 
    publisher VARCHAR(300), 
    scopus_source_id VARCHAR(40), 
    isi_listed BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_journal PRIMARY KEY (id), 
    CONSTRAINT uq_journal_eissn UNIQUE (eissn), 
    CONSTRAINT uq_journal_issn UNIQUE (issn)
);

CREATE TABLE lookup_value (
    id BIGSERIAL NOT NULL, 
    list_code VARCHAR(60) NOT NULL, 
    code VARCHAR(60) NOT NULL, 
    label_en VARCHAR(200) NOT NULL, 
    label_ar VARCHAR(200), 
    sort_order INTEGER NOT NULL, 
    active BOOLEAN NOT NULL, 
    CONSTRAINT pk_lookup_value PRIMARY KEY (id), 
    CONSTRAINT uq_lookup_value_list_code_code UNIQUE (list_code, code)
);

CREATE INDEX ix_lookup_value_list_code ON lookup_value (list_code);

CREATE TABLE policy_version (
    id BIGSERIAL NOT NULL, 
    code VARCHAR(40) NOT NULL, 
    title VARCHAR(300) NOT NULL, 
    effective_from DATE NOT NULL, 
    effective_to DATE, 
    document_path VARCHAR(500), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_policy_version PRIMARY KEY (id), 
    CONSTRAINT uq_policy_version_code UNIQUE (code)
);

CREATE TABLE referee (
    id BIGSERIAL NOT NULL, 
    full_name VARCHAR(200) NOT NULL, 
    email VARCHAR(254), 
    university VARCHAR(300) NOT NULL, 
    country_code VARCHAR(2) NOT NULL, 
    rank rank NOT NULL, 
    scopus_author_id VARCHAR(40), 
    openalex_author_id VARCHAR(40), 
    h_index INTEGER, 
    citation_count INTEGER, 
    topics JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_referee PRIMARY KEY (id), 
    CONSTRAINT uq_referee_email UNIQUE (email), 
    CONSTRAINT uq_referee_openalex_author_id UNIQUE (openalex_author_id)
);

CREATE TABLE department (
    id BIGSERIAL NOT NULL, 
    college_id BIGINT NOT NULL, 
    code VARCHAR(20) NOT NULL, 
    name_en VARCHAR(200) NOT NULL, 
    name_ar VARCHAR(200), 
    awards_degrees BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_department PRIMARY KEY (id), 
    CONSTRAINT fk_department_college_id_college FOREIGN KEY(college_id) REFERENCES college (id), 
    CONSTRAINT uq_department_code UNIQUE (code)
);

CREATE INDEX ix_department_college_id ON department (college_id);

CREATE TABLE journal_ranking (
    id BIGSERIAL NOT NULL, 
    journal_id BIGINT NOT NULL, 
    year SMALLINT NOT NULL, 
    scopus_indexed BOOLEAN NOT NULL, 
    sjr_category VARCHAR(200) NOT NULL, 
    sjr_percentile NUMERIC(5, 2), 
    quartile SMALLINT, 
    impact_factor NUMERIC(7, 3), 
    CONSTRAINT pk_journal_ranking PRIMARY KEY (id), 
    CONSTRAINT ck_journal_ranking_quartile_range CHECK (quartile BETWEEN 1 AND 4), 
    CONSTRAINT ck_journal_ranking_percentile_range CHECK (sjr_percentile BETWEEN 0 AND 100), 
    CONSTRAINT fk_journal_ranking_journal_id_journal FOREIGN KEY(journal_id) REFERENCES journal (id) ON DELETE CASCADE, 
    CONSTRAINT uq_journal_ranking_journal_id_year_sjr_category UNIQUE (journal_id, year, sjr_category)
);

CREATE INDEX ix_journal_ranking_journal_id ON journal_ranking (journal_id);

CREATE TABLE policy_chunk (
    id BIGSERIAL NOT NULL, 
    policy_version_id BIGINT NOT NULL, 
    area criterionarea NOT NULL, 
    section_ref VARCHAR(60), 
    page SMALLINT, 
    text TEXT NOT NULL, 
    tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED NOT NULL, 
    embedding VECTOR(1536), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_policy_chunk PRIMARY KEY (id), 
    CONSTRAINT fk_policy_chunk_policy_version_id_policy_version FOREIGN KEY(policy_version_id) REFERENCES policy_version (id)
);

CREATE INDEX ix_policy_chunk_embedding ON policy_chunk USING hnsw (embedding vector_cosine_ops);

CREATE INDEX ix_policy_chunk_policy_version_id ON policy_chunk (policy_version_id);

CREATE INDEX ix_policy_chunk_tsv ON policy_chunk USING gin (tsv);

CREATE TABLE promotion_criteria (
    id BIGSERIAL NOT NULL, 
    policy_version_id BIGINT NOT NULL, 
    track promotiontrack NOT NULL, 
    min_years_in_rank SMALLINT NOT NULL, 
    min_years_at_institution SMALLINT NOT NULL, 
    early_application_months SMALLINT NOT NULL, 
    exceptional_min_years SMALLINT NOT NULL, 
    reapply_min_years SMALLINT NOT NULL, 
    reapply_new_publications SMALLINT NOT NULL, 
    reapply_new_class_a SMALLINT NOT NULL, 
    reapply_new_main_author SMALLINT NOT NULL, 
    min_total_publications SMALLINT NOT NULL, 
    min_sole_main_author SMALLINT NOT NULL, 
    min_published SMALLINT NOT NULL, 
    min_at_institution SMALLINT NOT NULL, 
    min_class_a_main_author SMALLINT NOT NULL, 
    max_supervision_rule_papers SMALLINT NOT NULL, 
    max_books_total SMALLINT NOT NULL, 
    max_patents SMALLINT NOT NULL, 
    max_creative_works SMALLINT NOT NULL, 
    min_referee_reports SMALLINT NOT NULL, 
    min_referee_average_pct NUMERIC(5, 2) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_promotion_criteria PRIMARY KEY (id), 
    CONSTRAINT fk_promotion_criteria_policy_version_id_policy_version FOREIGN KEY(policy_version_id) REFERENCES policy_version (id), 
    CONSTRAINT uq_promotion_criteria_policy_version_id_track UNIQUE (policy_version_id, track)
);

CREATE TABLE research_item_cap (
    id BIGSERIAL NOT NULL, 
    policy_version_id BIGINT NOT NULL, 
    track promotiontrack NOT NULL, 
    item_type VARCHAR(40) NOT NULL, 
    max_count SMALLINT NOT NULL, 
    counts_as_class journalclass, 
    CONSTRAINT pk_research_item_cap PRIMARY KEY (id), 
    CONSTRAINT fk_research_item_cap_policy_version_id_policy_version FOREIGN KEY(policy_version_id) REFERENCES policy_version (id), 
    CONSTRAINT uq_research_item_cap_policy_version_id_track_item_type UNIQUE (policy_version_id, track, item_type)
);

CREATE TABLE rubric (
    id BIGSERIAL NOT NULL, 
    policy_version_id BIGINT NOT NULL, 
    code rubriccode NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    total_points NUMERIC(5, 1) NOT NULL, 
    pass_points NUMERIC(5, 1) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_rubric PRIMARY KEY (id), 
    CONSTRAINT fk_rubric_policy_version_id_policy_version FOREIGN KEY(policy_version_id) REFERENCES policy_version (id), 
    CONSTRAINT uq_rubric_policy_version_id_code UNIQUE (policy_version_id, code)
);

CREATE TABLE app_user (
    id BIGSERIAL NOT NULL, 
    email VARCHAR(254) NOT NULL, 
    auth_provider authprovider NOT NULL, 
    password_hash VARCHAR(255), 
    external_subject VARCHAR(255), 
    full_name VARCHAR(200), 
    employee_id VARCHAR(40), 
    profile_completed_at TIMESTAMP WITH TIME ZONE, 
    college_id BIGINT, 
    department_id BIGINT, 
    is_active BOOLEAN NOT NULL, 
    failed_login_count INTEGER NOT NULL, 
    locked_until TIMESTAMP WITH TIME ZONE, 
    last_login_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_app_user PRIMARY KEY (id), 
    CONSTRAINT ck_app_user_credentials_match_provider CHECK ((auth_provider = 'local' AND password_hash IS NOT NULL) OR (auth_provider = 'oidc' AND external_subject IS NOT NULL)), 
    CONSTRAINT fk_app_user_college_id_college FOREIGN KEY(college_id) REFERENCES college (id), 
    CONSTRAINT fk_app_user_department_id_department FOREIGN KEY(department_id) REFERENCES department (id), 
    CONSTRAINT uq_app_user_email UNIQUE (email), 
    CONSTRAINT uq_app_user_employee_id UNIQUE (employee_id), 
    CONSTRAINT uq_app_user_external_subject UNIQUE (external_subject)
);

CREATE TABLE rubric_item (
    id BIGSERIAL NOT NULL, 
    rubric_id BIGINT NOT NULL, 
    item_no SMALLINT NOT NULL, 
    text_en TEXT NOT NULL, 
    text_ar TEXT, 
    min_points NUMERIC(4, 1) NOT NULL, 
    max_points NUMERIC(4, 1) NOT NULL, 
    full_professor_only BOOLEAN NOT NULL, 
    redistributable BOOLEAN NOT NULL, 
    CONSTRAINT pk_rubric_item PRIMARY KEY (id), 
    CONSTRAINT ck_rubric_item_points_range CHECK (min_points >= 0 AND max_points >= min_points), 
    CONSTRAINT fk_rubric_item_rubric_id_rubric FOREIGN KEY(rubric_id) REFERENCES rubric (id) ON DELETE CASCADE, 
    CONSTRAINT uq_rubric_item_rubric_id_item_no UNIQUE (rubric_id, item_no)
);

CREATE TABLE auth_session (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    user_agent VARCHAR(300), 
    CONSTRAINT pk_auth_session PRIMARY KEY (id), 
    CONSTRAINT fk_auth_session_user_id_app_user FOREIGN KEY(user_id) REFERENCES app_user (id) ON DELETE CASCADE, 
    CONSTRAINT uq_auth_session_token_hash UNIQUE (token_hash)
);

CREATE INDEX ix_auth_session_user_id ON auth_session (user_id);

CREATE TABLE promotion_case (
    id BIGSERIAL NOT NULL, 
    applicant_id BIGINT NOT NULL, 
    policy_version_id BIGINT NOT NULL, 
    track promotiontrack NOT NULL, 
    academic_year VARCHAR(9) NOT NULL, 
    status casestatus NOT NULL, 
    specialization VARCHAR(200), 
    fine_specialization VARCHAR(200), 
    research_keywords VARCHAR(80)[], 
    appointment_date DATE, 
    rank_on_appointment rank, 
    current_rank rank, 
    current_rank_date DATE, 
    scopus_author_id VARCHAR(40), 
    orcid VARCHAR(19), 
    openalex_author_id VARCHAR(40), 
    phd_outside_uae BOOLEAN, 
    early_application BOOLEAN NOT NULL, 
    exceptional_case BOOLEAN NOT NULL, 
    exceptional_justification TEXT, 
    previously_rejected BOOLEAN NOT NULL, 
    rejection_date DATE, 
    decl_not_from_thesis BOOLEAN NOT NULL, 
    decl_after_current_rank BOOLEAN NOT NULL, 
    application_signed_date DATE, 
    submitted_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_promotion_case PRIMARY KEY (id), 
    CONSTRAINT ck_promotion_case_exceptional_needs_justification CHECK (NOT exceptional_case OR exceptional_justification IS NOT NULL), 
    CONSTRAINT ck_promotion_case_rejection_needs_date CHECK (NOT previously_rejected OR rejection_date IS NOT NULL), 
    CONSTRAINT fk_promotion_case_applicant_id_app_user FOREIGN KEY(applicant_id) REFERENCES app_user (id), 
    CONSTRAINT fk_promotion_case_policy_version_id_policy_version FOREIGN KEY(policy_version_id) REFERENCES policy_version (id)
);

CREATE INDEX ix_promotion_case_applicant_id ON promotion_case (applicant_id);

CREATE INDEX ix_promotion_case_status ON promotion_case (status);

CREATE TABLE researcher_profile (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT NOT NULL, 
    source profilesource NOT NULL, 
    external_author_id VARCHAR(60) NOT NULL, 
    h_index INTEGER, 
    citation_count INTEGER, 
    works_count INTEGER, 
    topics JSONB, 
    coauthors JSONB, 
    affiliations JSONB, 
    last_synced_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_researcher_profile PRIMARY KEY (id), 
    CONSTRAINT fk_researcher_profile_user_id_app_user FOREIGN KEY(user_id) REFERENCES app_user (id) ON DELETE CASCADE, 
    CONSTRAINT uq_researcher_profile_user_id_source UNIQUE (user_id, source)
);

CREATE TABLE user_role (
    id BIGSERIAL NOT NULL, 
    user_id BIGINT NOT NULL, 
    role role_name NOT NULL, 
    department_id BIGINT, 
    college_id BIGINT, 
    valid_from DATE, 
    valid_to DATE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_user_role PRIMARY KEY (id), 
    CONSTRAINT ck_user_role_dean_has_college CHECK (role <> 'dean' OR college_id IS NOT NULL), 
    CONSTRAINT ck_user_role_hod_has_department CHECK (role <> 'hod' OR department_id IS NOT NULL), 
    CONSTRAINT fk_user_role_college_id_college FOREIGN KEY(college_id) REFERENCES college (id), 
    CONSTRAINT fk_user_role_department_id_department FOREIGN KEY(department_id) REFERENCES department (id), 
    CONSTRAINT fk_user_role_user_id_app_user FOREIGN KEY(user_id) REFERENCES app_user (id) ON DELETE CASCADE, 
    CONSTRAINT uq_user_role_user_id_role_department_id_college_id UNIQUE (user_id, role, department_id, college_id)
);

CREATE INDEX ix_user_role_user_id ON user_role (user_id);

CREATE TABLE administrative_position (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    position_id BIGINT NOT NULL, 
    unit VARCHAR(300) NOT NULL, 
    date_from DATE NOT NULL, 
    date_to DATE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_administrative_position PRIMARY KEY (id), 
    CONSTRAINT fk_administrative_position_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_administrative_position_position_id_lookup_value FOREIGN KEY(position_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_administrative_position_case_id ON administrative_position (case_id);

CREATE TABLE advising_semester (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    academic_year VARCHAR(9) NOT NULL, 
    semester semester NOT NULL, 
    advisees SMALLINT NOT NULL, 
    meetings_held SMALLINT NOT NULL, 
    on_warning_at_start SMALLINT NOT NULL, 
    cleared_warning SMALLINT NOT NULL, 
    improved_gpa SMALLINT NOT NULL, 
    notes TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_advising_semester PRIMARY KEY (id), 
    CONSTRAINT ck_advising_semester_non_negative CHECK (advisees >= 0 AND meetings_held >= 0), 
    CONSTRAINT ck_advising_semester_cleared_le_warning CHECK (cleared_warning <= on_warning_at_start), 
    CONSTRAINT ck_advising_semester_improved_le_remaining CHECK (improved_gpa <= on_warning_at_start - cleared_warning), 
    CONSTRAINT fk_advising_semester_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE
);

CREATE INDEX ix_advising_semester_case_id ON advising_semester (case_id);

CREATE TABLE agent_run (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    component component NOT NULL, 
    status runstatus NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    model_name VARCHAR(100), 
    prompt_version VARCHAR(40), 
    input_hash VARCHAR(64), 
    error TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_agent_run PRIMARY KEY (id), 
    CONSTRAINT fk_agent_run_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE
);

CREATE INDEX ix_agent_run_case_id ON agent_run (case_id);

CREATE TABLE audit_log_entry (
    id BIGSERIAL NOT NULL, 
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    user_id BIGINT, 
    case_id BIGINT, 
    action VARCHAR(64) NOT NULL, 
    entity_table VARCHAR(64), 
    entity_id BIGINT, 
    before JSONB, 
    after JSONB, 
    detail TEXT, 
    CONSTRAINT pk_audit_log_entry PRIMARY KEY (id), 
    CONSTRAINT fk_audit_log_entry_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE SET NULL, 
    CONSTRAINT fk_audit_log_entry_user_id_app_user FOREIGN KEY(user_id) REFERENCES app_user (id)
);

CREATE INDEX ix_audit_log_entry_case_id ON audit_log_entry (case_id);

CREATE INDEX ix_audit_log_entry_entity ON audit_log_entry (entity_table, entity_id);

CREATE INDEX ix_audit_log_entry_occurred_at ON audit_log_entry (occurred_at);

CREATE TABLE award (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    name VARCHAR(300) NOT NULL, 
    awarding_body VARCHAR(300) NOT NULL, 
    year SMALLINT NOT NULL, 
    scope_id BIGINT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_award PRIMARY KEY (id), 
    CONSTRAINT fk_award_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_award_scope_id_lookup_value FOREIGN KEY(scope_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_award_case_id ON award (case_id);

CREATE TABLE book (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    item_type bookitemtype NOT NULL, 
    book_title VARCHAR(600) NOT NULL, 
    chapter_title VARCHAR(600), 
    publisher VARCHAR(300) NOT NULL, 
    publication_date DATE NOT NULL, 
    isbn VARCHAR(17) NOT NULL, 
    main_or_sole_author BOOLEAN NOT NULL, 
    financial_support_by VARCHAR(300), 
    refereed BOOLEAN NOT NULL, 
    referee_count SMALLINT, 
    from_thesis BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_book PRIMARY KEY (id), 
    CONSTRAINT ck_book_chapter_has_title CHECK (item_type <> 'chapter' OR chapter_title IS NOT NULL), 
    CONSTRAINT ck_book_heritage_refereed CHECK (item_type <> 'heritage' OR referee_count IS NOT NULL), 
    CONSTRAINT fk_book_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE
);

CREATE INDEX ix_book_case_id ON book (case_id);

CREATE TABLE case_document (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    section_code VARCHAR(8) NOT NULL, 
    entity_table VARCHAR(64), 
    entity_id BIGINT, 
    kind documentkind NOT NULL, 
    original_filename VARCHAR(300) NOT NULL, 
    stored_path VARCHAR(500) NOT NULL, 
    mime_type VARCHAR(100) NOT NULL, 
    size_bytes INTEGER NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    signed_date DATE, 
    uploaded_by BIGINT NOT NULL, 
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    superseded_by_id BIGINT, 
    CONSTRAINT pk_case_document PRIMARY KEY (id), 
    CONSTRAINT ck_case_document_entity_pair CHECK ((entity_table IS NULL) = (entity_id IS NULL)), 
    CONSTRAINT ck_case_document_size_limit CHECK (size_bytes > 0 AND size_bytes <= 26214400), 
    CONSTRAINT fk_case_document_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_case_document_superseded_by_id_case_document FOREIGN KEY(superseded_by_id) REFERENCES case_document (id), 
    CONSTRAINT fk_case_document_uploaded_by_app_user FOREIGN KEY(uploaded_by) REFERENCES app_user (id)
);

CREATE INDEX ix_case_document_case_id ON case_document (case_id);

CREATE INDEX ix_case_document_entity ON case_document (entity_table, entity_id);

CREATE TABLE case_report (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    version INTEGER NOT NULL, 
    overall_pass BOOLEAN, 
    content JSONB NOT NULL, 
    rendered_path VARCHAR(500), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_case_report PRIMARY KEY (id), 
    CONSTRAINT fk_case_report_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT uq_case_report_case_id_version UNIQUE (case_id, version)
);

CREATE INDEX ix_case_report_case_id ON case_report (case_id);

CREATE TABLE case_status_history (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    from_status casestatus, 
    to_status casestatus NOT NULL, 
    changed_by BIGINT, 
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    note TEXT, 
    CONSTRAINT pk_case_status_history PRIMARY KEY (id), 
    CONSTRAINT fk_case_status_history_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_case_status_history_changed_by_app_user FOREIGN KEY(changed_by) REFERENCES app_user (id)
);

CREATE INDEX ix_case_status_history_case_id ON case_status_history (case_id);

CREATE TABLE committee_membership (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    committee_name VARCHAR(300) NOT NULL, 
    level orglevel NOT NULL, 
    role_id BIGINT NOT NULL, 
    date_from DATE NOT NULL, 
    date_to DATE, 
    contribution_summary TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_committee_membership PRIMARY KEY (id), 
    CONSTRAINT fk_committee_membership_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_committee_membership_role_id_lookup_value FOREIGN KEY(role_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_committee_membership_case_id ON committee_membership (case_id);

CREATE TABLE conference_paper (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    title VARCHAR(600) NOT NULL, 
    conference_title VARCHAR(400) NOT NULL, 
    organizer VARCHAR(300) NOT NULL, 
    conference_date DATE NOT NULL, 
    place VARCHAR(200) NOT NULL, 
    pages VARCHAR(30), 
    main_or_sole_author BOOLEAN NOT NULL, 
    scopus_indexed BOOLEAN NOT NULL, 
    doi VARCHAR(200), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_conference_paper PRIMARY KEY (id), 
    CONSTRAINT fk_conference_paper_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE
);

CREATE INDEX ix_conference_paper_case_id ON conference_paper (case_id);

CREATE TABLE course_taught (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    academic_year VARCHAR(9) NOT NULL, 
    semester semester NOT NULL, 
    course_code VARCHAR(20) NOT NULL, 
    course_title VARCHAR(300) NOT NULL, 
    level courselevel NOT NULL, 
    sections SMALLINT NOT NULL, 
    students SMALLINT NOT NULL, 
    role teachingrole NOT NULL, 
    delivery_mode deliverymode NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_course_taught PRIMARY KEY (id), 
    CONSTRAINT ck_course_taught_counts CHECK (sections >= 1 AND students >= 0), 
    CONSTRAINT fk_course_taught_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE
);

CREATE INDEX ix_course_taught_case_id ON course_taught (case_id);

CREATE INDEX ix_course_taught_course_code ON course_taught (course_code);

CREATE TABLE creative_work (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    form_id BIGINT NOT NULL, 
    title VARCHAR(400) NOT NULL, 
    venue VARCHAR(300) NOT NULL, 
    organizing_institution VARCHAR(300) NOT NULL, 
    date_from DATE NOT NULL, 
    date_to DATE, 
    approved BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_creative_work PRIMARY KEY (id), 
    CONSTRAINT fk_creative_work_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_creative_work_form_id_lookup_value FOREIGN KEY(form_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_creative_work_case_id ON creative_work (case_id);

CREATE TABLE curriculum_contribution (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    contribution_type_id BIGINT NOT NULL, 
    course_or_program VARCHAR(300) NOT NULL, 
    changes VARCHAR(60)[], 
    self_classification developmentdepth, 
    description TEXT NOT NULL, 
    approved_by orglevel NOT NULL, 
    approval_date DATE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_curriculum_contribution PRIMARY KEY (id), 
    CONSTRAINT fk_curriculum_contribution_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_curriculum_contribution_contribution_type_id_lookup_value FOREIGN KEY(contribution_type_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_curriculum_contribution_case_id ON curriculum_contribution (case_id);

CREATE TABLE dean_evaluation (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    teaching_text TEXT, 
    teaching_rating deanrating, 
    research_text TEXT, 
    research_rating deanrating, 
    service_text TEXT, 
    service_rating deanrating, 
    approved_by BIGINT, 
    approved_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_dean_evaluation PRIMARY KEY (id), 
    CONSTRAINT fk_dean_evaluation_approved_by_app_user FOREIGN KEY(approved_by) REFERENCES app_user (id), 
    CONSTRAINT fk_dean_evaluation_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT uq_dean_evaluation_case_id UNIQUE (case_id)
);

CREATE INDEX ix_dean_evaluation_case_id ON dean_evaluation (case_id);

CREATE TABLE degree (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    level degreelevel NOT NULL, 
    specialization VARCHAR(200) NOT NULL, 
    university VARCHAR(300) NOT NULL, 
    country_code VARCHAR(2) NOT NULL, 
    study_from DATE NOT NULL, 
    study_to DATE, 
    graduation_date DATE NOT NULL, 
    thesis_title VARCHAR(500), 
    equivalency_required BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_degree PRIMARY KEY (id), 
    CONSTRAINT ck_degree_study_period CHECK (study_to IS NULL OR study_to >= study_from), 
    CONSTRAINT fk_degree_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE
);

CREATE INDEX ix_degree_case_id ON degree (case_id);

CREATE TABLE funded_project (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    title VARCHAR(400) NOT NULL, 
    funding_body VARCHAR(300) NOT NULL, 
    funder_type_id BIGINT NOT NULL, 
    role investigatorrole NOT NULL, 
    amount NUMERIC(14, 2), 
    currency VARCHAR(3), 
    start_date DATE NOT NULL, 
    end_date DATE, 
    status projectstatus NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_funded_project PRIMARY KEY (id), 
    CONSTRAINT fk_funded_project_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_funded_project_funder_type_id_lookup_value FOREIGN KEY(funder_type_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_funded_project_case_id ON funded_project (case_id);

CREATE TABLE gate_decision (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    gate gate NOT NULL, 
    decided_by BIGINT NOT NULL, 
    outcome gateoutcome NOT NULL, 
    comment TEXT, 
    sections_to_revise VARCHAR(8)[], 
    decided_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_gate_decision PRIMARY KEY (id), 
    CONSTRAINT ck_gate_decision_revision_names_sections CHECK (outcome <> 'return_for_revision' OR sections_to_revise IS NOT NULL), 
    CONSTRAINT fk_gate_decision_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_gate_decision_decided_by_app_user FOREIGN KEY(decided_by) REFERENCES app_user (id)
);

CREATE INDEX ix_gate_decision_case_id ON gate_decision (case_id);

CREATE TABLE journal_criteria_confirmation (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    journal_name VARCHAR(400) NOT NULL, 
    issn VARCHAR(9), 
    publisher_type_id BIGINT NOT NULL, 
    specialised_editorial_board BOOLEAN NOT NULL, 
    peer_review_two_referees BOOLEAN NOT NULL, 
    years_regular_publication SMALLINT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_journal_criteria_confirmation PRIMARY KEY (id), 
    CONSTRAINT fk_journal_criteria_confirmation_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_journal_criteria_confirmation_publisher_type_id_lookup_value FOREIGN KEY(publisher_type_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_journal_criteria_confirmation_case_id ON journal_criteria_confirmation (case_id);

CREATE TABLE non_academic_position (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    position VARCHAR(200) NOT NULL, 
    employer VARCHAR(300) NOT NULL, 
    country_code VARCHAR(2) NOT NULL, 
    date_from DATE NOT NULL, 
    date_to DATE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_non_academic_position PRIMARY KEY (id), 
    CONSTRAINT fk_non_academic_position_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE
);

CREATE INDEX ix_non_academic_position_case_id ON non_academic_position (case_id);

CREATE TABLE patent (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    title VARCHAR(400) NOT NULL, 
    patent_number VARCHAR(60) NOT NULL, 
    office_id BIGINT NOT NULL, 
    status patentstatus NOT NULL, 
    grant_date DATE, 
    inventors TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_patent PRIMARY KEY (id), 
    CONSTRAINT ck_patent_granted_has_date CHECK (status <> 'granted' OR grant_date IS NOT NULL), 
    CONSTRAINT fk_patent_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_patent_office_id_lookup_value FOREIGN KEY(office_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_patent_case_id ON patent (case_id);

CREATE TABLE policy_contribution (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    policy_name VARCHAR(300) NOT NULL, 
    level orglevel NOT NULL, 
    role_id BIGINT NOT NULL, 
    activity_date DATE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_policy_contribution PRIMARY KEY (id), 
    CONSTRAINT fk_policy_contribution_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_policy_contribution_role_id_lookup_value FOREIGN KEY(role_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_policy_contribution_case_id ON policy_contribution (case_id);

CREATE TABLE rank_history (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    rank rank NOT NULL, 
    date_obtained DATE NOT NULL, 
    university VARCHAR(300) NOT NULL, 
    country_code VARCHAR(2) NOT NULL, 
    held_from DATE NOT NULL, 
    held_to DATE, 
    at_this_university BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_rank_history PRIMARY KEY (id), 
    CONSTRAINT ck_rank_history_held_period CHECK (held_to IS NULL OR held_to >= held_from), 
    CONSTRAINT fk_rank_history_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE
);

CREATE INDEX ix_rank_history_case_id ON rank_history (case_id);

CREATE TABLE recommendation_letter (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    writer_name VARCHAR(200) NOT NULL, 
    writer_rank VARCHAR(100) NOT NULL, 
    writer_institution VARCHAR(300) NOT NULL, 
    relationship_id BIGINT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_recommendation_letter PRIMARY KEY (id), 
    CONSTRAINT fk_recommendation_letter_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_recommendation_letter_relationship_id_lookup_value FOREIGN KEY(relationship_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_recommendation_letter_case_id ON recommendation_letter (case_id);

CREATE TABLE referee_candidate (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    referee_id BIGINT NOT NULL, 
    match_score NUMERIC(4, 3), 
    match_rationale TEXT, 
    coi_coauthor BOOLEAN NOT NULL, 
    coi_same_institution BOOLEAN NOT NULL, 
    coi_used_within_5_years BOOLEAN NOT NULL, 
    eligible BOOLEAN NOT NULL, 
    selected_by_chancellor BOOLEAN NOT NULL, 
    selected_by BIGINT, 
    selected_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_referee_candidate PRIMARY KEY (id), 
    CONSTRAINT fk_referee_candidate_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_referee_candidate_referee_id_referee FOREIGN KEY(referee_id) REFERENCES referee (id), 
    CONSTRAINT fk_referee_candidate_selected_by_app_user FOREIGN KEY(selected_by) REFERENCES app_user (id), 
    CONSTRAINT uq_referee_candidate_case_id_referee_id UNIQUE (case_id, referee_id)
);

CREATE INDEX ix_referee_candidate_case_id ON referee_candidate (case_id);

CREATE TABLE scopus_evidence (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    h_index INTEGER NOT NULL, 
    total_citations INTEGER NOT NULL, 
    screenshot_date DATE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_scopus_evidence PRIMARY KEY (id), 
    CONSTRAINT ck_scopus_evidence_non_negative CHECK (h_index >= 0 AND total_citations >= 0), 
    CONSTRAINT fk_scopus_evidence_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT uq_scopus_evidence_case_id UNIQUE (case_id)
);

CREATE INDEX ix_scopus_evidence_case_id ON scopus_evidence (case_id);

CREATE TABLE supervision (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    student_name VARCHAR(200) NOT NULL, 
    degree graduatedegree NOT NULL, 
    role supervisionrole NOT NULL, 
    thesis_title VARCHAR(600) NOT NULL, 
    start_date DATE NOT NULL, 
    status supervisionstatus NOT NULL, 
    graduation_date DATE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_supervision PRIMARY KEY (id), 
    CONSTRAINT ck_supervision_graduated_has_date CHECK (status <> 'graduated' OR graduation_date IS NOT NULL), 
    CONSTRAINT fk_supervision_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE
);

CREATE INDEX ix_supervision_case_id ON supervision (case_id);

CREATE TABLE teaching_development (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    title VARCHAR(300) NOT NULL, 
    format activityformat NOT NULL, 
    topic_id BIGINT NOT NULL, 
    organizer VARCHAR(300) NOT NULL, 
    activity_date DATE NOT NULL, 
    hours NUMERIC(5, 1), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_teaching_development PRIMARY KEY (id), 
    CONSTRAINT fk_teaching_development_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_teaching_development_topic_id_lookup_value FOREIGN KEY(topic_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_teaching_development_case_id ON teaching_development (case_id);

CREATE TABLE training_delivered (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    title VARCHAR(300) NOT NULL, 
    inside_university BOOLEAN NOT NULL, 
    host_organisation VARCHAR(300) NOT NULL, 
    activity_date DATE NOT NULL, 
    hours NUMERIC(5, 1), 
    participants INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_training_delivered PRIMARY KEY (id), 
    CONSTRAINT fk_training_delivered_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE
);

CREATE INDEX ix_training_delivered_case_id ON training_delivered (case_id);

CREATE TABLE workshop_delivered (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    title VARCHAR(300) NOT NULL, 
    organized_by orglevel NOT NULL, 
    role workshoprole NOT NULL, 
    activity_date DATE NOT NULL, 
    attendees INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_workshop_delivered PRIMARY KEY (id), 
    CONSTRAINT fk_workshop_delivered_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE
);

CREATE INDEX ix_workshop_delivered_case_id ON workshop_delivered (case_id);

CREATE TABLE agent_assessment (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    agent_run_id BIGINT NOT NULL, 
    component component NOT NULL, 
    verdict verdict NOT NULL, 
    narrative TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_agent_assessment PRIMARY KEY (id), 
    CONSTRAINT fk_agent_assessment_agent_run_id_agent_run FOREIGN KEY(agent_run_id) REFERENCES agent_run (id) ON DELETE CASCADE, 
    CONSTRAINT fk_agent_assessment_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT uq_agent_assessment_agent_run_id UNIQUE (agent_run_id)
);

CREATE INDEX ix_agent_assessment_case_id ON agent_assessment (case_id);

CREATE TABLE community_activity (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    activity_type_id BIGINT NOT NULL, 
    funded_project_id BIGINT, 
    title VARCHAR(300) NOT NULL, 
    beneficiary_organisation VARCHAR(300) NOT NULL, 
    applicant_role VARCHAR(200) NOT NULL, 
    date_from DATE NOT NULL, 
    date_to DATE, 
    beneficiaries INTEGER, 
    deliverables TEXT NOT NULL, 
    measurable_outcome TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_community_activity PRIMARY KEY (id), 
    CONSTRAINT fk_community_activity_activity_type_id_lookup_value FOREIGN KEY(activity_type_id) REFERENCES lookup_value (id), 
    CONSTRAINT fk_community_activity_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_community_activity_funded_project_id_funded_project FOREIGN KEY(funded_project_id) REFERENCES funded_project (id) ON DELETE SET NULL
);

CREATE INDEX ix_community_activity_case_id ON community_activity (case_id);

CREATE TABLE course_file (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    course_taught_id BIGINT NOT NULL, 
    is_coordinator BOOLEAN NOT NULL, 
    kept_in_id BIGINT NOT NULL, 
    items VARCHAR(60)[] NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_course_file PRIMARY KEY (id), 
    CONSTRAINT fk_course_file_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_course_file_course_taught_id_course_taught FOREIGN KEY(course_taught_id) REFERENCES course_taught (id) ON DELETE CASCADE, 
    CONSTRAINT fk_course_file_kept_in_id_lookup_value FOREIGN KEY(kept_in_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_course_file_case_id ON course_file (case_id);

CREATE TABLE peer_observation (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    course_taught_id BIGINT NOT NULL, 
    observer_role_id BIGINT NOT NULL, 
    observer_name VARCHAR(200), 
    observation_date DATE NOT NULL, 
    rating NUMERIC(6, 2) NOT NULL, 
    scale_max NUMERIC(6, 2) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_peer_observation PRIMARY KEY (id), 
    CONSTRAINT ck_peer_observation_rating_in_scale CHECK (rating >= 0 AND rating <= scale_max), 
    CONSTRAINT fk_peer_observation_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_peer_observation_course_taught_id_course_taught FOREIGN KEY(course_taught_id) REFERENCES course_taught (id) ON DELETE CASCADE, 
    CONSTRAINT fk_peer_observation_observer_role_id_lookup_value FOREIGN KEY(observer_role_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_peer_observation_case_id ON peer_observation (case_id);

CREATE TABLE publication (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    submit_for_promotion BOOLEAN NOT NULL, 
    lookup_source lookupsource NOT NULL, 
    doi VARCHAR(200), 
    openalex_work_id VARCHAR(40), 
    title VARCHAR(600) NOT NULL, 
    journal_id BIGINT, 
    journal_name VARCHAR(400) NOT NULL, 
    issn VARCHAR(9), 
    publisher VARCHAR(300) NOT NULL, 
    volume VARCHAR(20), 
    issue VARCHAR(20), 
    pages VARCHAR(30), 
    language language NOT NULL, 
    status publicationstatus NOT NULL, 
    issue_date DATE, 
    acceptance_date DATE, 
    new_since_rejection BOOLEAN, 
    author_position SMALLINT NOT NULL, 
    total_authors SMALLINT NOT NULL, 
    applicant_role authorrole NOT NULL, 
    main_author_basis mainauthorbasis, 
    main_author_explanation TEXT, 
    with_supervised_student BOOLEAN NOT NULL, 
    supervision_id BIGINT, 
    at_this_university BOOLEAN NOT NULL, 
    from_thesis BOOLEAN NOT NULL, 
    impact_factor NUMERIC(7, 3), 
    disputes_class BOOLEAN NOT NULL, 
    dispute_reason TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_publication PRIMARY KEY (id), 
    CONSTRAINT ck_publication_main_has_basis CHECK (applicant_role <> 'main' OR main_author_basis IS NOT NULL), 
    CONSTRAINT ck_publication_other_explained CHECK (main_author_basis <> 'other' OR main_author_explanation IS NOT NULL), 
    CONSTRAINT ck_publication_accepted_has_date CHECK (status <> 'accepted' OR acceptance_date IS NOT NULL), 
    CONSTRAINT ck_publication_published_has_issue_date CHECK (status <> 'published' OR issue_date IS NOT NULL), 
    CONSTRAINT ck_publication_supervision_linked CHECK (NOT with_supervised_student OR supervision_id IS NOT NULL), 
    CONSTRAINT ck_publication_author_position_range CHECK (author_position BETWEEN 1 AND total_authors), 
    CONSTRAINT fk_publication_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_publication_journal_id_journal FOREIGN KEY(journal_id) REFERENCES journal (id), 
    CONSTRAINT fk_publication_supervision_id_supervision FOREIGN KEY(supervision_id) REFERENCES supervision (id)
);

CREATE INDEX ix_publication_case_id ON publication (case_id);

CREATE INDEX ix_publication_doi ON publication (doi);

CREATE INDEX ix_publication_journal_id ON publication (journal_id);

CREATE TABLE reviewer_assignment (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    referee_id BIGINT NOT NULL, 
    candidate_id BIGINT, 
    status assignmentstatus NOT NULL, 
    invited_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_reminder_at TIMESTAMP WITH TIME ZONE, 
    responded_at TIMESTAMP WITH TIME ZONE, 
    report_received_at TIMESTAMP WITH TIME ZONE, 
    replaced_by_id BIGINT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_reviewer_assignment PRIMARY KEY (id), 
    CONSTRAINT fk_reviewer_assignment_candidate_id_referee_candidate FOREIGN KEY(candidate_id) REFERENCES referee_candidate (id) ON DELETE SET NULL, 
    CONSTRAINT fk_reviewer_assignment_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_reviewer_assignment_referee_id_referee FOREIGN KEY(referee_id) REFERENCES referee (id), 
    CONSTRAINT fk_reviewer_assignment_replaced_by_id_reviewer_assignment FOREIGN KEY(replaced_by_id) REFERENCES reviewer_assignment (id)
);

CREATE INDEX ix_reviewer_assignment_case_id ON reviewer_assignment (case_id);

CREATE INDEX ix_reviewer_assignment_referee_invited ON reviewer_assignment (referee_id, invited_at);

CREATE TABLE rubric_score (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    rubric_item_id BIGINT NOT NULL, 
    suggested_points NUMERIC(4, 1) NOT NULL, 
    suggested_by_run_id BIGINT, 
    suggestion_basis decisionbasis NOT NULL, 
    suggestion_rationale TEXT, 
    confidence confidence, 
    hod_points NUMERIC(4, 1), 
    hod_user_id BIGINT, 
    hod_at TIMESTAMP WITH TIME ZONE, 
    dean_points NUMERIC(4, 1), 
    dean_user_id BIGINT, 
    dean_at TIMESTAMP WITH TIME ZONE, 
    change_reason TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_rubric_score PRIMARY KEY (id), 
    CONSTRAINT ck_rubric_score_non_negative CHECK (suggested_points >= 0 AND (hod_points IS NULL OR hod_points >= 0) AND (dean_points IS NULL OR dean_points >= 0)), 
    CONSTRAINT fk_rubric_score_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_rubric_score_dean_user_id_app_user FOREIGN KEY(dean_user_id) REFERENCES app_user (id), 
    CONSTRAINT fk_rubric_score_hod_user_id_app_user FOREIGN KEY(hod_user_id) REFERENCES app_user (id), 
    CONSTRAINT fk_rubric_score_rubric_item_id_rubric_item FOREIGN KEY(rubric_item_id) REFERENCES rubric_item (id), 
    CONSTRAINT fk_rubric_score_suggested_by_run_id_agent_run FOREIGN KEY(suggested_by_run_id) REFERENCES agent_run (id) ON DELETE SET NULL, 
    CONSTRAINT uq_rubric_score_case_id_rubric_item_id UNIQUE (case_id, rubric_item_id)
);

CREATE INDEX ix_rubric_score_case_id ON rubric_score (case_id);

CREATE TABLE student_satisfaction (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    course_taught_id BIGINT NOT NULL, 
    respondents SMALLINT NOT NULL, 
    average_score NUMERIC(6, 2) NOT NULL, 
    scale_max NUMERIC(6, 2) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_student_satisfaction PRIMARY KEY (id), 
    CONSTRAINT ck_student_satisfaction_score_in_scale CHECK (average_score >= 0 AND average_score <= scale_max), 
    CONSTRAINT fk_student_satisfaction_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_student_satisfaction_course_taught_id_course_taught FOREIGN KEY(course_taught_id) REFERENCES course_taught (id) ON DELETE CASCADE
);

CREATE INDEX ix_student_satisfaction_case_id ON student_satisfaction (case_id);

CREATE TABLE teaching_innovation (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    innovation_type_id BIGINT NOT NULL, 
    course_taught_id BIGINT NOT NULL, 
    description TEXT NOT NULL, 
    measured_outcome TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_teaching_innovation PRIMARY KEY (id), 
    CONSTRAINT fk_teaching_innovation_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_teaching_innovation_course_taught_id_course_taught FOREIGN KEY(course_taught_id) REFERENCES course_taught (id) ON DELETE CASCADE, 
    CONSTRAINT fk_teaching_innovation_innovation_type_id_lookup_value FOREIGN KEY(innovation_type_id) REFERENCES lookup_value (id)
);

CREATE INDEX ix_teaching_innovation_case_id ON teaching_innovation (case_id);

CREATE TABLE claim (
    id BIGSERIAL NOT NULL, 
    assessment_id BIGINT NOT NULL, 
    text TEXT NOT NULL, 
    value NUMERIC(10, 2), 
    source_table VARCHAR(64) NOT NULL, 
    source_ids BIGINT[] NOT NULL, 
    verified BOOLEAN, 
    verification_note TEXT, 
    retry_count SMALLINT NOT NULL, 
    CONSTRAINT pk_claim PRIMARY KEY (id), 
    CONSTRAINT fk_claim_assessment_id_agent_assessment FOREIGN KEY(assessment_id) REFERENCES agent_assessment (id) ON DELETE CASCADE
);

CREATE INDEX ix_claim_assessment_id ON claim (assessment_id);

CREATE TABLE coauthored_paper_evaluation (
    id BIGSERIAL NOT NULL, 
    publication_id BIGINT NOT NULL, 
    coauthor_order VARCHAR(100), 
    applicant_score NUMERIC(5, 2), 
    senior_coauthor_score NUMERIC(5, 2), 
    decision VARCHAR(100), 
    rank VARCHAR(40), 
    CONSTRAINT pk_coauthored_paper_evaluation PRIMARY KEY (id), 
    CONSTRAINT fk_coauthored_paper_evaluation_publication_id_publication FOREIGN KEY(publication_id) REFERENCES publication (id) ON DELETE CASCADE, 
    CONSTRAINT uq_coauthored_paper_evaluation_publication_id UNIQUE (publication_id)
);

CREATE TABLE criterion_result (
    id BIGSERIAL NOT NULL, 
    assessment_id BIGINT NOT NULL, 
    criterion_key VARCHAR(60) NOT NULL, 
    label VARCHAR(200) NOT NULL, 
    required_value NUMERIC(8, 2), 
    actual_value NUMERIC(8, 2), 
    passed BOOLEAN, 
    policy_ref VARCHAR(60), 
    CONSTRAINT pk_criterion_result PRIMARY KEY (id), 
    CONSTRAINT fk_criterion_result_assessment_id_agent_assessment FOREIGN KEY(assessment_id) REFERENCES agent_assessment (id) ON DELETE CASCADE
);

CREATE INDEX ix_criterion_result_assessment_id ON criterion_result (assessment_id);

CREATE TABLE flag (
    id BIGSERIAL NOT NULL, 
    case_id BIGINT NOT NULL, 
    assessment_id BIGINT, 
    severity flagseverity NOT NULL, 
    code VARCHAR(64) NOT NULL, 
    message TEXT NOT NULL, 
    entity_table VARCHAR(64), 
    entity_id BIGINT, 
    resolved_by BIGINT, 
    resolved_at TIMESTAMP WITH TIME ZONE, 
    resolution_note TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_flag PRIMARY KEY (id), 
    CONSTRAINT fk_flag_assessment_id_agent_assessment FOREIGN KEY(assessment_id) REFERENCES agent_assessment (id) ON DELETE SET NULL, 
    CONSTRAINT fk_flag_case_id_promotion_case FOREIGN KEY(case_id) REFERENCES promotion_case (id) ON DELETE CASCADE, 
    CONSTRAINT fk_flag_resolved_by_app_user FOREIGN KEY(resolved_by) REFERENCES app_user (id)
);

CREATE INDEX ix_flag_case_id ON flag (case_id);

CREATE TABLE item_result (
    id BIGSERIAL NOT NULL, 
    assessment_id BIGINT NOT NULL, 
    entity_table VARCHAR(64) NOT NULL, 
    entity_id BIGINT NOT NULL, 
    counted BOOLEAN, 
    classification VARCHAR(60), 
    credited_role VARCHAR(60), 
    basis decisionbasis NOT NULL, 
    confidence confidence, 
    reason TEXT, 
    CONSTRAINT pk_item_result PRIMARY KEY (id), 
    CONSTRAINT fk_item_result_assessment_id_agent_assessment FOREIGN KEY(assessment_id) REFERENCES agent_assessment (id) ON DELETE CASCADE
);

CREATE INDEX ix_item_result_assessment_id ON item_result (assessment_id);

CREATE TABLE outreach_message (
    id BIGSERIAL NOT NULL, 
    assignment_id BIGINT NOT NULL, 
    kind messagekind NOT NULL, 
    subject VARCHAR(300) NOT NULL, 
    body TEXT NOT NULL, 
    scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    delivery_status deliverystatus NOT NULL, 
    CONSTRAINT pk_outreach_message PRIMARY KEY (id), 
    CONSTRAINT fk_outreach_message_assignment_id_reviewer_assignment FOREIGN KEY(assignment_id) REFERENCES reviewer_assignment (id) ON DELETE CASCADE
);

CREATE INDEX ix_outreach_message_assignment_id ON outreach_message (assignment_id);

CREATE TABLE publication_author (
    id BIGSERIAL NOT NULL, 
    publication_id BIGINT NOT NULL, 
    position SMALLINT NOT NULL, 
    display_name VARCHAR(200) NOT NULL, 
    openalex_author_id VARCHAR(40), 
    is_applicant BOOLEAN NOT NULL, 
    CONSTRAINT pk_publication_author PRIMARY KEY (id), 
    CONSTRAINT fk_publication_author_publication_id_publication FOREIGN KEY(publication_id) REFERENCES publication (id) ON DELETE CASCADE, 
    CONSTRAINT uq_publication_author_publication_id_position UNIQUE (publication_id, position)
);

CREATE INDEX ix_publication_author_openalex_author_id ON publication_author (openalex_author_id);

CREATE INDEX ix_publication_author_publication_id ON publication_author (publication_id);

CREATE TABLE referee_report (
    id BIGSERIAL NOT NULL, 
    assignment_id BIGINT NOT NULL, 
    recommendation TEXT, 
    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_referee_report PRIMARY KEY (id), 
    CONSTRAINT fk_referee_report_assignment_id_reviewer_assignment FOREIGN KEY(assignment_id) REFERENCES reviewer_assignment (id) ON DELETE CASCADE, 
    CONSTRAINT uq_referee_report_assignment_id UNIQUE (assignment_id)
);

CREATE TABLE referee_paper_grade (
    id BIGSERIAL NOT NULL, 
    report_id BIGINT NOT NULL, 
    publication_id BIGINT NOT NULL, 
    grade_pct NUMERIC(5, 2) NOT NULL, 
    CONSTRAINT pk_referee_paper_grade PRIMARY KEY (id), 
    CONSTRAINT ck_referee_paper_grade_grade_range CHECK (grade_pct BETWEEN 0 AND 100), 
    CONSTRAINT fk_referee_paper_grade_publication_id_publication FOREIGN KEY(publication_id) REFERENCES publication (id) ON DELETE CASCADE, 
    CONSTRAINT fk_referee_paper_grade_report_id_referee_report FOREIGN KEY(report_id) REFERENCES referee_report (id) ON DELETE CASCADE, 
    CONSTRAINT uq_referee_paper_grade_report_id_publication_id UNIQUE (report_id, publication_id)
);

CREATE INDEX ix_referee_paper_grade_report_id ON referee_paper_grade (report_id);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

