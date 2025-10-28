--
-- PostgreSQL database dump
--

\restrict liAvbkkTZ5o4EKalVUbiR5C1eYSIs4Gjxt0l9RBNsAC9bHwjEbjrWEeXvunis5W

-- Dumped from database version 15.14
-- Dumped by pg_dump version 15.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: accesslevel; Type: TYPE; Schema: public; Owner: uk_bot
--

CREATE TYPE public.accesslevel AS ENUM (
    'APARTMENT',
    'HOUSE',
    'YARD'
);


ALTER TYPE public.accesslevel OWNER TO uk_bot;

--
-- Name: documenttype; Type: TYPE; Schema: public; Owner: uk_bot
--

CREATE TYPE public.documenttype AS ENUM (
    'PASSPORT',
    'PROPERTY_DEED',
    'RENTAL_AGREEMENT',
    'UTILITY_BILL',
    'OTHER'
);


ALTER TYPE public.documenttype OWNER TO uk_bot;

--
-- Name: verificationstatus; Type: TYPE; Schema: public; Owner: uk_bot
--

CREATE TYPE public.verificationstatus AS ENUM (
    'PENDING',
    'APPROVED',
    'REJECTED',
    'REQUESTED'
);


ALTER TYPE public.verificationstatus OWNER TO uk_bot;

--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: uk_bot
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_updated_at_column() OWNER TO uk_bot;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: access_rights; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.access_rights (
    id integer NOT NULL,
    user_id integer NOT NULL,
    access_level character varying(50) NOT NULL,
    apartment_number character varying(20),
    house_number character varying(20),
    yard_name character varying(100),
    is_active boolean DEFAULT true,
    expires_at timestamp with time zone,
    granted_by integer NOT NULL,
    granted_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.access_rights OWNER TO uk_bot;

--
-- Name: access_rights_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.access_rights_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.access_rights_id_seq OWNER TO uk_bot;

--
-- Name: access_rights_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.access_rights_id_seq OWNED BY public.access_rights.id;


--
-- Name: apartments; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.apartments (
    id integer NOT NULL,
    building_id integer NOT NULL,
    apartment_number character varying(20) NOT NULL,
    entrance integer,
    floor integer,
    rooms_count integer,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_by integer,
    updated_at timestamp with time zone,
    area double precision
);


ALTER TABLE public.apartments OWNER TO uk_bot;

--
-- Name: apartments_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.apartments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.apartments_id_seq OWNER TO uk_bot;

--
-- Name: apartments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.apartments_id_seq OWNED BY public.apartments.id;


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.audit_logs (
    id integer NOT NULL,
    user_id bigint,
    action character varying(100) NOT NULL,
    details json,
    ip_address character varying(45),
    created_at timestamp with time zone DEFAULT now(),
    telegram_user_id bigint
);


ALTER TABLE public.audit_logs OWNER TO uk_bot;

--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.audit_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.audit_logs_id_seq OWNER TO uk_bot;

--
-- Name: audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;


--
-- Name: buildings; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.buildings (
    id integer NOT NULL,
    address character varying(300) NOT NULL,
    yard_id integer NOT NULL,
    gps_latitude double precision,
    gps_longitude double precision,
    entrance_count integer DEFAULT 1 NOT NULL,
    floor_count integer DEFAULT 1 NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_by integer,
    updated_at timestamp with time zone
);


ALTER TABLE public.buildings OWNER TO uk_bot;

--
-- Name: buildings_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.buildings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.buildings_id_seq OWNER TO uk_bot;

--
-- Name: buildings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.buildings_id_seq OWNED BY public.buildings.id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    user_id integer NOT NULL,
    notification_type character varying(50) NOT NULL,
    title character varying(255),
    content text NOT NULL,
    is_read boolean,
    is_sent boolean,
    meta_data json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


ALTER TABLE public.notifications OWNER TO uk_bot;

--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.notifications_id_seq OWNER TO uk_bot;

--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
-- Name: planning_conflicts; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.planning_conflicts (
    id integer NOT NULL,
    quarterly_plan_id integer NOT NULL,
    conflict_type character varying(100) NOT NULL,
    status character varying(50) NOT NULL,
    involved_schedule_ids json,
    involved_user_ids json,
    conflict_time timestamp with time zone,
    conflict_date date,
    conflict_details json,
    description text,
    suggested_resolutions json,
    applied_resolution json,
    resolved_at timestamp with time zone,
    resolved_by integer,
    priority integer NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


ALTER TABLE public.planning_conflicts OWNER TO uk_bot;

--
-- Name: planning_conflicts_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.planning_conflicts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.planning_conflicts_id_seq OWNER TO uk_bot;

--
-- Name: planning_conflicts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.planning_conflicts_id_seq OWNED BY public.planning_conflicts.id;


--
-- Name: quarterly_plans; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.quarterly_plans (
    id integer NOT NULL,
    year integer NOT NULL,
    quarter integer NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    created_by integer NOT NULL,
    status character varying(50) NOT NULL,
    specializations json,
    coverage_24_7 boolean NOT NULL,
    load_balancing_enabled boolean NOT NULL,
    auto_transfers_enabled boolean NOT NULL,
    notifications_enabled boolean NOT NULL,
    total_shifts_planned integer NOT NULL,
    total_hours_planned double precision NOT NULL,
    coverage_percentage double precision NOT NULL,
    total_conflicts integer NOT NULL,
    resolved_conflicts integer NOT NULL,
    pending_conflicts integer NOT NULL,
    settings json,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    activated_at timestamp with time zone,
    archived_at timestamp with time zone
);


ALTER TABLE public.quarterly_plans OWNER TO uk_bot;

--
-- Name: quarterly_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.quarterly_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.quarterly_plans_id_seq OWNER TO uk_bot;

--
-- Name: quarterly_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.quarterly_plans_id_seq OWNED BY public.quarterly_plans.id;


--
-- Name: quarterly_shift_schedules; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.quarterly_shift_schedules (
    id integer NOT NULL,
    quarterly_plan_id integer NOT NULL,
    planned_date date NOT NULL,
    planned_start_time timestamp with time zone NOT NULL,
    planned_end_time timestamp with time zone NOT NULL,
    assigned_user_id integer,
    specialization character varying(100) NOT NULL,
    schedule_type character varying(50) NOT NULL,
    status character varying(50) NOT NULL,
    actual_shift_id integer,
    shift_config json,
    coverage_areas json,
    priority integer NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


ALTER TABLE public.quarterly_shift_schedules OWNER TO uk_bot;

--
-- Name: quarterly_shift_schedules_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.quarterly_shift_schedules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.quarterly_shift_schedules_id_seq OWNER TO uk_bot;

--
-- Name: quarterly_shift_schedules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.quarterly_shift_schedules_id_seq OWNED BY public.quarterly_shift_schedules.id;


--
-- Name: ratings; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.ratings (
    id integer NOT NULL,
    request_number character varying(10) NOT NULL,
    user_id integer NOT NULL,
    rating integer NOT NULL,
    review text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.ratings OWNER TO uk_bot;

--
-- Name: ratings_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.ratings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.ratings_id_seq OWNER TO uk_bot;

--
-- Name: ratings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.ratings_id_seq OWNED BY public.ratings.id;


--
-- Name: request_assignments; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.request_assignments (
    id integer NOT NULL,
    request_number character varying(10) NOT NULL,
    assignment_type character varying(20) NOT NULL,
    group_specialization character varying(100),
    executor_id integer,
    status character varying(20),
    created_at timestamp with time zone DEFAULT now(),
    created_by integer NOT NULL
);


ALTER TABLE public.request_assignments OWNER TO uk_bot;

--
-- Name: request_assignments_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.request_assignments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.request_assignments_id_seq OWNER TO uk_bot;

--
-- Name: request_assignments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.request_assignments_id_seq OWNED BY public.request_assignments.id;


--
-- Name: request_comments; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.request_comments (
    id integer NOT NULL,
    request_number character varying(10) NOT NULL,
    user_id integer NOT NULL,
    comment_text text NOT NULL,
    comment_type character varying(50) NOT NULL,
    previous_status character varying(50),
    new_status character varying(50),
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.request_comments OWNER TO uk_bot;

--
-- Name: request_comments_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.request_comments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.request_comments_id_seq OWNER TO uk_bot;

--
-- Name: request_comments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.request_comments_id_seq OWNED BY public.request_comments.id;


--
-- Name: requests; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.requests (
    request_number character varying(10) NOT NULL,
    user_id integer NOT NULL,
    category character varying(100) NOT NULL,
    status character varying(50) NOT NULL,
    address text,
    description text NOT NULL,
    apartment character varying(20),
    urgency character varying(20) NOT NULL,
    media_files json,
    executor_id integer,
    notes text,
    completion_report text,
    completion_media json,
    assignment_type character varying(20),
    assigned_group character varying(100),
    assigned_at timestamp with time zone,
    assigned_by integer,
    purchase_materials text,
    requested_materials text,
    manager_materials_comment text,
    purchase_history text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    completed_at timestamp with time zone,
    apartment_id integer,
    is_returned boolean DEFAULT false NOT NULL,
    return_reason text,
    return_media jsonb,
    returned_at timestamp with time zone,
    returned_by integer,
    manager_confirmed boolean DEFAULT false NOT NULL,
    manager_confirmed_by integer,
    manager_confirmed_at timestamp with time zone,
    manager_confirmation_notes text
);


ALTER TABLE public.requests OWNER TO uk_bot;

--
-- Name: shift_assignments; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.shift_assignments (
    id integer NOT NULL,
    shift_id integer NOT NULL,
    request_number character varying(10) NOT NULL,
    assignment_priority integer NOT NULL,
    estimated_duration integer,
    assignment_order integer,
    ai_score double precision,
    confidence_level double precision,
    specialization_match_score double precision,
    geographic_score double precision,
    workload_score double precision,
    status character varying(50) NOT NULL,
    auto_assigned boolean NOT NULL,
    confirmed_by_executor boolean NOT NULL,
    assigned_at timestamp with time zone DEFAULT now(),
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    planned_start_at timestamp with time zone,
    planned_completion_at timestamp with time zone,
    assignment_reason character varying(200),
    notes text,
    executor_instructions text,
    actual_duration integer,
    execution_quality_rating double precision,
    had_issues boolean NOT NULL,
    issues_description text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


ALTER TABLE public.shift_assignments OWNER TO uk_bot;

--
-- Name: shift_assignments_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.shift_assignments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.shift_assignments_id_seq OWNER TO uk_bot;

--
-- Name: shift_assignments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.shift_assignments_id_seq OWNED BY public.shift_assignments.id;


--
-- Name: shift_schedules; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.shift_schedules (
    id integer NOT NULL,
    date date NOT NULL,
    planned_coverage json,
    actual_coverage json,
    planned_specialization_coverage json,
    actual_specialization_coverage json,
    predicted_requests integer,
    actual_requests integer NOT NULL,
    prediction_accuracy double precision,
    recommended_shifts integer,
    actual_shifts integer NOT NULL,
    optimization_score double precision,
    coverage_percentage double precision,
    load_balance_score double precision,
    special_conditions json,
    manual_adjustments json,
    notes character varying(500),
    status character varying(50) NOT NULL,
    created_by integer,
    auto_generated boolean NOT NULL,
    version integer NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


ALTER TABLE public.shift_schedules OWNER TO uk_bot;

--
-- Name: shift_schedules_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.shift_schedules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.shift_schedules_id_seq OWNER TO uk_bot;

--
-- Name: shift_schedules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.shift_schedules_id_seq OWNED BY public.shift_schedules.id;


--
-- Name: shift_templates; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.shift_templates (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    start_hour integer NOT NULL,
    start_minute integer NOT NULL,
    duration_hours integer NOT NULL,
    required_specializations json,
    min_executors integer NOT NULL,
    max_executors integer NOT NULL,
    default_max_requests integer NOT NULL,
    coverage_areas json,
    geographic_zone character varying(100),
    priority_level integer NOT NULL,
    auto_create boolean NOT NULL,
    days_of_week json,
    advance_days integer NOT NULL,
    is_active boolean NOT NULL,
    default_shift_type character varying(50) NOT NULL,
    settings json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


ALTER TABLE public.shift_templates OWNER TO uk_bot;

--
-- Name: shift_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.shift_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.shift_templates_id_seq OWNER TO uk_bot;

--
-- Name: shift_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.shift_templates_id_seq OWNED BY public.shift_templates.id;


--
-- Name: shift_transfers; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.shift_transfers (
    id integer NOT NULL,
    shift_id integer NOT NULL,
    from_executor_id integer NOT NULL,
    to_executor_id integer,
    status character varying(50) NOT NULL,
    reason character varying(100) NOT NULL,
    comment text,
    urgency_level character varying(20) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    assigned_at timestamp without time zone,
    responded_at timestamp without time zone,
    completed_at timestamp without time zone,
    auto_assigned boolean NOT NULL,
    retry_count integer NOT NULL,
    max_retries integer NOT NULL
);


ALTER TABLE public.shift_transfers OWNER TO uk_bot;

--
-- Name: shift_transfers_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.shift_transfers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.shift_transfers_id_seq OWNER TO uk_bot;

--
-- Name: shift_transfers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.shift_transfers_id_seq OWNED BY public.shift_transfers.id;


--
-- Name: shifts; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.shifts (
    id integer NOT NULL,
    user_id integer,
    start_time timestamp with time zone NOT NULL,
    end_time timestamp with time zone,
    status character varying(50) NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    shift_type character varying(50) DEFAULT 'regular'::character varying,
    max_requests integer DEFAULT 10,
    current_request_count integer DEFAULT 0,
    priority_level integer DEFAULT 1,
    efficiency_score double precision,
    planned_start_time timestamp with time zone,
    planned_end_time timestamp with time zone,
    specialization_focus jsonb,
    coverage_areas jsonb,
    completed_requests integer DEFAULT 0,
    average_response_time double precision,
    quality_rating double precision,
    shift_template_id integer,
    geographic_zone character varying(100),
    average_completion_time double precision
);


ALTER TABLE public.shifts OWNER TO uk_bot;

--
-- Name: shifts_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.shifts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.shifts_id_seq OWNER TO uk_bot;

--
-- Name: shifts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.shifts_id_seq OWNED BY public.shifts.id;


--
-- Name: user_apartments; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.user_apartments (
    id integer NOT NULL,
    user_id integer NOT NULL,
    apartment_id integer NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    requested_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    reviewed_at timestamp with time zone,
    reviewed_by integer,
    admin_comment text,
    is_owner boolean DEFAULT false NOT NULL,
    is_primary boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);


ALTER TABLE public.user_apartments OWNER TO uk_bot;

--
-- Name: user_apartments_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.user_apartments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.user_apartments_id_seq OWNER TO uk_bot;

--
-- Name: user_apartments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.user_apartments_id_seq OWNED BY public.user_apartments.id;


--
-- Name: user_documents; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.user_documents (
    id integer NOT NULL,
    user_id integer NOT NULL,
    document_type character varying(50) NOT NULL,
    file_id character varying(255) NOT NULL,
    file_name character varying(255),
    file_size integer,
    verification_status character varying(50) DEFAULT 'pending'::character varying,
    verification_notes text,
    verified_by integer,
    verified_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.user_documents OWNER TO uk_bot;

--
-- Name: user_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.user_documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.user_documents_id_seq OWNER TO uk_bot;

--
-- Name: user_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.user_documents_id_seq OWNED BY public.user_documents.id;


--
-- Name: user_verifications; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.user_verifications (
    id integer NOT NULL,
    user_id integer NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying,
    requested_info jsonb DEFAULT '{}'::jsonb,
    requested_at timestamp with time zone,
    requested_by integer,
    admin_notes text,
    verified_by integer,
    verified_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.user_verifications OWNER TO uk_bot;

--
-- Name: user_verifications_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.user_verifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.user_verifications_id_seq OWNER TO uk_bot;

--
-- Name: user_verifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.user_verifications_id_seq OWNED BY public.user_verifications.id;


--
-- Name: user_yards; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.user_yards (
    id integer NOT NULL,
    user_id integer NOT NULL,
    yard_id integer NOT NULL,
    granted_at timestamp with time zone DEFAULT now() NOT NULL,
    granted_by integer,
    comment text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


ALTER TABLE public.user_yards OWNER TO uk_bot;

--
-- Name: user_yards_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.user_yards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.user_yards_id_seq OWNER TO uk_bot;

--
-- Name: user_yards_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.user_yards_id_seq OWNED BY public.user_yards.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.users (
    id integer NOT NULL,
    telegram_id bigint NOT NULL,
    username character varying(255),
    first_name character varying(255),
    last_name character varying(255),
    role character varying(50) NOT NULL,
    roles text,
    active_role character varying(50),
    status character varying(50) NOT NULL,
    language character varying(10) NOT NULL,
    phone character varying(20),
    specialization text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    verification_status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    verification_notes text,
    verification_date timestamp with time zone,
    verified_by integer,
    passport_series character varying(10),
    passport_number character varying(10),
    birth_date timestamp with time zone
);


ALTER TABLE public.users OWNER TO uk_bot;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.users_id_seq OWNER TO uk_bot;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: yards; Type: TABLE; Schema: public; Owner: uk_bot
--

CREATE TABLE public.yards (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    gps_latitude double precision,
    gps_longitude double precision,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_by integer,
    updated_at timestamp with time zone
);


ALTER TABLE public.yards OWNER TO uk_bot;

--
-- Name: yards_id_seq; Type: SEQUENCE; Schema: public; Owner: uk_bot
--

CREATE SEQUENCE public.yards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.yards_id_seq OWNER TO uk_bot;

--
-- Name: yards_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: uk_bot
--

ALTER SEQUENCE public.yards_id_seq OWNED BY public.yards.id;


--
-- Name: access_rights id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.access_rights ALTER COLUMN id SET DEFAULT nextval('public.access_rights_id_seq'::regclass);


--
-- Name: apartments id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.apartments ALTER COLUMN id SET DEFAULT nextval('public.apartments_id_seq'::regclass);


--
-- Name: audit_logs id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq'::regclass);


--
-- Name: buildings id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.buildings ALTER COLUMN id SET DEFAULT nextval('public.buildings_id_seq'::regclass);


--
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
-- Name: planning_conflicts id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.planning_conflicts ALTER COLUMN id SET DEFAULT nextval('public.planning_conflicts_id_seq'::regclass);


--
-- Name: quarterly_plans id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.quarterly_plans ALTER COLUMN id SET DEFAULT nextval('public.quarterly_plans_id_seq'::regclass);


--
-- Name: quarterly_shift_schedules id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.quarterly_shift_schedules ALTER COLUMN id SET DEFAULT nextval('public.quarterly_shift_schedules_id_seq'::regclass);


--
-- Name: ratings id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.ratings ALTER COLUMN id SET DEFAULT nextval('public.ratings_id_seq'::regclass);


--
-- Name: request_assignments id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.request_assignments ALTER COLUMN id SET DEFAULT nextval('public.request_assignments_id_seq'::regclass);


--
-- Name: request_comments id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.request_comments ALTER COLUMN id SET DEFAULT nextval('public.request_comments_id_seq'::regclass);


--
-- Name: shift_assignments id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_assignments ALTER COLUMN id SET DEFAULT nextval('public.shift_assignments_id_seq'::regclass);


--
-- Name: shift_schedules id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_schedules ALTER COLUMN id SET DEFAULT nextval('public.shift_schedules_id_seq'::regclass);


--
-- Name: shift_templates id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_templates ALTER COLUMN id SET DEFAULT nextval('public.shift_templates_id_seq'::regclass);


--
-- Name: shift_transfers id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_transfers ALTER COLUMN id SET DEFAULT nextval('public.shift_transfers_id_seq'::regclass);


--
-- Name: shifts id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shifts ALTER COLUMN id SET DEFAULT nextval('public.shifts_id_seq'::regclass);


--
-- Name: user_apartments id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_apartments ALTER COLUMN id SET DEFAULT nextval('public.user_apartments_id_seq'::regclass);


--
-- Name: user_documents id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_documents ALTER COLUMN id SET DEFAULT nextval('public.user_documents_id_seq'::regclass);


--
-- Name: user_verifications id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_verifications ALTER COLUMN id SET DEFAULT nextval('public.user_verifications_id_seq'::regclass);


--
-- Name: user_yards id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_yards ALTER COLUMN id SET DEFAULT nextval('public.user_yards_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: yards id; Type: DEFAULT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.yards ALTER COLUMN id SET DEFAULT nextval('public.yards_id_seq'::regclass);


--
-- Data for Name: access_rights; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.access_rights (id, user_id, access_level, apartment_number, house_number, yard_name, is_active, expires_at, granted_by, granted_at, notes, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: apartments; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.apartments (id, building_id, apartment_number, entrance, floor, rooms_count, description, is_active, created_at, created_by, updated_at, area) FROM stdin;
1	1	1	1	1	\N	\N	t	2025-10-12 15:29:28.434617+00	2	\N	\N
2	1	54	2	9	5	\N	t	2025-10-12 15:30:05.633372+00	2	\N	122
55	1	2	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
56	1	3	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
58	1	5	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
59	1	6	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
60	1	7	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
61	1	8	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
62	1	9	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
63	1	10	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
64	1	11	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
65	1	12	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
66	1	13	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
67	1	14	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
68	1	15	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
69	1	16	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
70	1	17	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
71	1	18	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
72	1	19	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
73	1	20	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
74	1	21	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
75	1	22	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
76	1	23	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
77	1	24	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
78	1	25	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
79	1	26	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
80	1	27	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
81	1	28	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
82	1	29	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
83	1	30	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
84	1	31	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
85	1	32	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
86	1	33	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
87	1	34	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
88	1	35	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
89	1	36	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
90	1	37	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
91	1	38	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
92	1	39	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
93	1	40	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
94	1	41	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
95	1	42	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
96	1	43	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
97	1	44	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
98	1	45	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
99	1	46	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
100	1	47	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
101	1	48	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
102	1	49	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
103	1	50	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
104	1	51	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
105	1	52	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
106	1	53	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	\N	\N
57	1	4	\N	\N	\N	\N	t	2025-10-12 15:55:10.844688+00	2	2025-10-12 19:20:58.627335+00	\N
107	2	1	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
108	2	2	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
109	2	3	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
110	2	4	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
111	2	5	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
112	2	6	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
113	2	7	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
114	2	8	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
115	2	9	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
116	2	10	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
117	2	11	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
118	2	12	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
119	2	13	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
120	2	14	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
121	2	15	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
122	2	16	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
123	2	17	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
124	2	18	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
125	2	19	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
126	2	20	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
127	2	21	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
128	2	22	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
129	2	23	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
130	2	24	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
131	2	25	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
132	2	26	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
133	2	27	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
134	2	28	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
135	2	29	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
136	2	30	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
137	2	31	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
138	2	32	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
139	2	33	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
140	2	34	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
141	2	35	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
142	2	36	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
143	2	37	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
144	2	38	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
145	2	39	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
146	2	40	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
147	2	41	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
148	2	42	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
149	2	43	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
150	2	44	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
151	2	45	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
152	2	46	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
153	2	47	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
154	2	48	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
155	2	49	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
156	2	50	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
157	2	51	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
158	2	52	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
159	2	53	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
160	2	54	\N	\N	\N	\N	t	2025-10-12 19:24:51.312418+00	2	\N	\N
\.


--
-- Data for Name: audit_logs; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.audit_logs (id, user_id, action, details, ip_address, created_at, telegram_user_id) FROM stdin;
90	2	user_deleted	"{\\"deleted_user_id\\": 10, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": null, \\"status\\": \\"pending\\", \\"created_at\\": \\"2025-08-25 08:24:14.387904+00:00\\"}, \\"reason\\": \\"\\\\u0422\\\\u0435\\\\u0441\\\\u0442\\\\u043e\\\\u0432\\\\u043e\\\\u0435 \\\\u0443\\\\u0434\\\\u0430\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u0435 - \\\\u043f\\\\u043e\\\\u043b\\\\u044c\\\\u0437\\\\u043e\\\\u0432\\\\u0430\\\\u0442\\\\u0435\\\\u043b\\\\u044c \\\\u043d\\\\u0435 \\\\u0434\\\\u043e\\\\u043b\\\\u0436\\\\u0435\\\\u043d \\\\u0431\\\\u044b\\\\u0442\\\\u044c \\\\u0432 \\\\u0441\\\\u0438\\\\u0441\\\\u0442\\\\u0435\\\\u043c\\\\u0435\\", \\"timestamp\\": \\"2025-08-25 08:29:27.648948+00:00\\"}"	\N	2025-08-25 08:29:27.648948+00	6055402868
97	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756117847, \\"nonce\\": \\"HduVfqE_hAv0AoQnP006yw\\", \\"specialization\\": \\"hvac\\"}"	\N	2025-08-25 09:30:47.384031+00	48617336
98	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756117847, \\"nonce\\": \\"YusJKS8bHIyq96COO4WohA\\", \\"specialization\\": \\"hvac\\"}"	\N	2025-08-25 09:30:47.394248+00	48617336
99	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756121474, \\"nonce\\": \\"b7J8hWZBQUs2X6eBvaFroA\\", \\"specialization\\": \\"security\\"}"	\N	2025-08-25 10:31:14.772351+00	48617336
100	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756121474, \\"nonce\\": \\"nHztvVcZWB2QH1yj4PFTew\\", \\"specialization\\": \\"security\\"}"	\N	2025-08-25 10:31:14.781975+00	48617336
117	2	role_change	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"executor\\", \\"applicant\\", \\"manager\\"], \\"new_roles\\": [\\"executor\\"], \\"comment\\": \\"123123\\", \\"timestamp\\": \\"2025-08-25T19:41:27.104965\\"}"	\N	2025-08-25 19:41:27.093289+00	6055402868
118	2	role_change	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"executor\\"], \\"new_roles\\": [\\"applicant\\"], \\"comment\\": \\"23123\\", \\"timestamp\\": \\"2025-08-25T19:41:47.194892\\"}"	\N	2025-08-25 19:41:47.18384+00	6055402868
119	2	role_assigned	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"applicant\\"], \\"new_roles\\": [\\"applicant\\", \\"executor\\"], \\"assigned_role\\": \\"executor\\", \\"comment\\": \\"1231231\\", \\"timestamp\\": \\"2025-08-25 19:42:06.447958+00:00\\"}"	\N	2025-08-25 19:42:06.447958+00	6055402868
122	2	request_status_changed	{"request_id": 2, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 20:26:59.283436+00	48617336
125	2	request_status_changed	{"request_id": 8, "old_status": "\\u041d\\u043e\\u0432\\u0430\\u044f", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-08-25 20:34:36.765448+00	48617336
128	2	request_status_changed	{"request_id": 7, "old_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "new_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 20:37:11.678545+00	48617336
130	2	request_status_changed	{"request_id": 2, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 20:59:34.479305+00	48617336
132	2	request_status_changed	{"request_id": 9, "old_status": "\\u041d\\u043e\\u0432\\u0430\\u044f", "new_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 21:00:12.204276+00	6055402868
133	2	request_status_changed	{"request_id": 9, "old_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "new_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 21:04:00.575152+00	6055402868
134	2	request_status_changed	{"request_id": 7, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-08-25 21:06:54.045486+00	48617336
135	2	request_status_changed	{"request_id": 7, "old_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "new_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 21:06:56.494189+00	48617336
136	2	request_status_changed	{"request_id": 7, "old_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "new_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 21:06:58.891244+00	48617336
137	2	request_status_changed	{"request_id": 7, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 21:28:50.7867+00	48617336
138	2	role_assigned	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"applicant\\"], \\"new_roles\\": [\\"applicant\\", \\"executor\\"], \\"assigned_role\\": \\"executor\\", \\"comment\\": \\"s\\", \\"timestamp\\": \\"2025-08-30 12:36:47.223162+00:00\\"}"	\N	2025-08-30 12:36:47.223162+00	6055402868
139	2	role_removed	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"applicant\\", \\"executor\\"], \\"new_roles\\": [\\"executor\\"], \\"removed_role\\": \\"applicant\\", \\"comment\\": \\"s\\", \\"timestamp\\": \\"2025-08-30 12:36:47.249193+00:00\\"}"	\N	2025-08-30 12:36:47.249193+00	6055402868
140	2	specialization_change	"{\\"target_user_id\\": 11, \\"old_specializations\\": [\\"hvac\\", \\"electrician\\", \\"maintenance\\", \\"repair\\"], \\"new_specializations\\": [\\"hvac\\", \\"electrician\\", \\"maintenance\\", \\"repair\\", \\"plumber\\", \\"installation\\"], \\"comment\\": \\"s\\", \\"timestamp\\": \\"2025-08-30T12:37:08.206793\\"}"	\N	2025-08-30 12:37:08.196122+00	6055402868
141	2	role_assigned	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"executor\\"], \\"new_roles\\": [\\"executor\\", \\"applicant\\"], \\"assigned_role\\": \\"applicant\\", \\"comment\\": \\"\\\\u043e\\", \\"timestamp\\": \\"2025-08-30 13:54:51.874301+00:00\\"}"	\N	2025-08-30 13:54:51.874301+00	6055402868
142	2	role_removed	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"executor\\", \\"applicant\\"], \\"new_roles\\": [\\"applicant\\"], \\"removed_role\\": \\"executor\\", \\"comment\\": \\"\\\\u043e\\", \\"timestamp\\": \\"2025-08-30 13:54:51.888958+00:00\\"}"	\N	2025-08-30 13:54:51.888958+00	6055402868
143	2	role_assigned	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"applicant\\"], \\"new_roles\\": [\\"applicant\\", \\"executor\\"], \\"assigned_role\\": \\"executor\\", \\"comment\\": \\"\\\\u0434\\", \\"timestamp\\": \\"2025-08-30 14:03:15.195026+00:00\\"}"	\N	2025-08-30 14:03:15.195026+00	6055402868
155	2	invite_created	"{\\"role\\": \\"manager\\", \\"expires_at\\": 1758130621, \\"nonce\\": \\"-JFncwQLjMtYI0OCLYuk2w\\"}"	\N	2025-09-16 17:37:01.142325+00	48617336
87	2	user_deleted	"{\\"deleted_user_id\\": 9, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": \\"[\\\\\\"applicant\\\\\\"]\\", \\"status\\": \\"approved\\", \\"created_at\\": \\"2025-08-25 07:32:26.391723+00:00\\"}, \\"reason\\": \\"\\\\u0432\\\\u0430\\\\u044b\\\\u0432\\\\u0430\\", \\"timestamp\\": \\"2025-08-25 08:17:20.252436+00:00\\"}"	\N	2025-08-25 08:17:20.252436+00	6055402868
91	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756114441, \\"nonce\\": \\"zjzey0Sjz2J_Slup_7TILA\\", \\"specialization\\": \\"hvac\\"}"	\N	2025-08-25 08:34:01.164962+00	48617336
92	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756114441, \\"nonce\\": \\"yYaRuD8kTCw6vJ8YAqtcJA\\", \\"specialization\\": \\"hvac\\"}"	\N	2025-08-25 08:34:01.179068+00	48617336
111	2	role_change	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"executor\\", \\"applicant\\"], \\"new_roles\\": [\\"executor\\"], \\"comment\\": \\"12\\", \\"timestamp\\": \\"2025-08-25T19:38:06.394965\\"}"	\N	2025-08-25 19:38:06.387613+00	6055402868
112	2	role_change	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"executor\\"], \\"new_roles\\": [\\"executor\\", \\"applicant\\"], \\"comment\\": \\"1212\\", \\"timestamp\\": \\"2025-08-25T19:38:22.500115\\"}"	\N	2025-08-25 19:38:22.486996+00	6055402868
113	2	role_change	"{\\"target_user_id\\": 2, \\"old_roles\\": [\\"admin\\", \\"applicant\\", \\"executor\\", \\"manager\\"], \\"new_roles\\": [\\"admin\\", \\"executor\\"], \\"comment\\": \\"1212\\", \\"timestamp\\": \\"2025-08-25T19:39:20.109114\\"}"	\N	2025-08-25 19:39:20.099657+00	48617336
114	2	role_assigned	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"executor\\", \\"applicant\\"], \\"new_roles\\": [\\"executor\\", \\"applicant\\", \\"manager\\"], \\"assigned_role\\": \\"manager\\", \\"comment\\": \\"21212\\", \\"timestamp\\": \\"2025-08-25 19:39:48.003787+00:00\\"}"	\N	2025-08-25 19:39:48.003787+00	6055402868
123	2	request_status_changed	{"request_id": 2, "old_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "new_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 20:27:01.466345+00	48617336
126	2	request_status_changed	{"request_id": 8, "old_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "new_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 20:34:40.2065+00	48617336
129	2	role_removed	"{\\"target_user_id\\": 11, \\"old_roles\\": [\\"applicant\\", \\"executor\\"], \\"new_roles\\": [\\"applicant\\"], \\"removed_role\\": \\"executor\\", \\"comment\\": \\"He\\", \\"timestamp\\": \\"2025-08-25 20:49:57.111219+00:00\\"}"	\N	2025-08-25 20:49:57.111219+00	6055402868
131	2	request_status_changed	{"request_id": 2, "old_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "new_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 20:59:36.860273+00	48617336
154	2	invite_created	"{\\"role\\": \\"manager\\", \\"expires_at\\": 1758130621, \\"nonce\\": \\"20N802d5My9F-aiTfQFXzQ\\"}"	\N	2025-09-16 17:37:01.096179+00	48617336
1	2	role_switched	{"old_role": "admin", "new_role": "applicant"}	\N	2025-08-24 14:20:43.9294+00	48617336
2	2	role_switched	{"old_role": "applicant", "new_role": "admin"}	\N	2025-08-24 14:20:55.752043+00	48617336
3	2	role_switched	{"old_role": "admin", "new_role": "applicant"}	\N	2025-08-24 14:24:00.244015+00	48617336
4	2	role_switched	{"old_role": "applicant", "new_role": "manager"}	\N	2025-08-24 14:31:14.227537+00	48617336
5	2	request_status_changed	{"request_id": 3, "old_status": "\\u041d\\u043e\\u0432\\u0430\\u044f", "new_status": "\\u041e\\u0442\\u043c\\u0435\\u043d\\u0435\\u043d\\u0430", "notes": "[\\u0410\\u0434\\u043c\\u0438\\u043d\\u0438\\u0441\\u0442\\u0440\\u0430\\u0442\\u043e\\u0440] \\u041e\\u0442\\u043c\\u0435\\u043d\\u0430: Chai", "actor_role": "admin"}	\N	2025-08-24 14:31:22.725801+00	48617336
6	2	role_switched	{"old_role": "manager", "new_role": "executor"}	\N	2025-08-24 14:31:49.441578+00	48617336
7	2	role_switched	{"old_role": "executor", "new_role": "applicant"}	\N	2025-08-24 14:32:01.863458+00	48617336
8	2	role_switched	{"old_role": "applicant", "new_role": "manager"}	\N	2025-08-24 14:32:33.55645+00	48617336
9	2	request_status_changed	{"request_id": 4, "old_status": "\\u041d\\u043e\\u0432\\u0430\\u044f", "new_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "notes": "[\\u0410\\u0434\\u043c\\u0438\\u043d\\u0438\\u0441\\u0442\\u0440\\u0430\\u0442\\u043e\\u0440] \\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435: \\u0413\\u0438\\u0434\\u0435?", "actor_role": "admin"}	\N	2025-08-24 14:32:43.295981+00	48617336
10	2	role_switched	{"old_role": "manager", "new_role": "applicant"}	\N	2025-08-24 14:32:53.167062+00	48617336
11	2	role_switched	{"old_role": "applicant", "new_role": "manager"}	\N	2025-08-24 14:33:07.661521+00	48617336
12	2	role_switched	{"old_role": "manager", "new_role": "applicant"}	\N	2025-08-24 14:33:32.522176+00	48617336
13	2	role_switched	{"old_role": "applicant", "new_role": "manager"}	\N	2025-08-24 14:33:47.467833+00	48617336
14	2	role_switched	{"old_role": "manager", "new_role": "admin"}	\N	2025-08-24 14:34:18.824354+00	48617336
15	2	request_status_changed	{"request_id": 4, "old_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "new_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-24 14:35:38.194124+00	48617336
16	2	request_status_changed	{"request_id": 2, "old_status": "\\u041d\\u043e\\u0432\\u0430\\u044f", "new_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-24 14:35:46.54928+00	48617336
17	2	role_switched	{"old_role": "admin", "new_role": "applicant"}	\N	2025-08-24 14:35:53.722357+00	48617336
18	2	role_switched	{"old_role": "applicant", "new_role": "admin"}	\N	2025-08-24 14:44:16.172193+00	48617336
19	2	role_switched	{"old_role": "admin", "new_role": "manager"}	\N	2025-08-24 14:44:48.543848+00	48617336
20	2	role_switched	{"old_role": "manager", "new_role": "admin"}	\N	2025-08-24 15:06:31.933595+00	48617336
21	2	role_switched	{"old_role": "admin", "new_role": "admin"}	\N	2025-08-24 15:09:17.829169+00	48617336
22	2	role_switched	{"old_role": "admin", "new_role": "admin"}	\N	2025-08-24 15:38:54.890583+00	48617336
23	2	role_switched	{"old_role": "admin", "new_role": "admin"}	\N	2025-08-24 15:40:18.803652+00	48617336
24	2	role_switched	{"old_role": "admin", "new_role": "admin"}	\N	2025-08-24 15:40:31.398745+00	48617336
25	2	role_switched	{"old_role": "admin", "new_role": "admin"}	\N	2025-08-24 15:40:52.297693+00	48617336
26	2	role_switched	{"old_role": "admin", "new_role": "admin"}	\N	2025-08-24 15:41:36.48222+00	48617336
27	2	role_switched	{"old_role": "admin", "new_role": "executor"}	\N	2025-08-24 15:41:54.16304+00	48617336
28	2	role_switched	{"old_role": "executor", "new_role": "manager"}	\N	2025-08-24 15:42:05.322093+00	48617336
30	2	user_approved	"{\\"target_user_id\\": 1, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"88\\", \\"timestamp\\": \\"2025-08-24 17:01:54.555157+00:00\\"}"	\N	2025-08-24 17:01:54.555157+00	48617336
31	2	role_assigned	"{\\"target_user_id\\": 1, \\"old_roles\\": [], \\"new_roles\\": [\\"applicant\\"], \\"assigned_role\\": \\"applicant\\", \\"comment\\": \\"11\\", \\"timestamp\\": \\"2025-08-24 17:05:32.136005+00:00\\"}"	\N	2025-08-24 17:05:32.136005+00	48617336
32	2	user_deleted	"{\\"deleted_user_id\\": 1, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": \\"[\\\\\\"applicant\\\\\\"]\\", \\"status\\": \\"approved\\", \\"created_at\\": \\"2025-08-24 14:02:23.351048+00:00\\"}, \\"reason\\": \\"232\\", \\"timestamp\\": \\"2025-08-24 17:08:27.748069+00:00\\"}"	\N	2025-08-24 17:08:27.748069+00	48617336
33	2	request_status_changed	{"request_id": 4, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-08-24 17:13:34.334951+00	48617336
34	2	request_status_changed	{"request_id": 4, "old_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "new_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-24 17:53:05.701905+00	48617336
37	2	user_deleted	"{\\"deleted_user_id\\": 3, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": null, \\"status\\": \\"pending\\", \\"created_at\\": \\"2025-08-24 17:08:44.817987+00:00\\"}, \\"reason\\": \\"1\\", \\"timestamp\\": \\"2025-08-24 20:10:30.208814+00:00\\"}"	\N	2025-08-24 20:10:30.208814+00	48617336
38	2	user_approved	"{\\"target_user_id\\": 4, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"\\\\u043e\\\\u043a\\\\u0435\\", \\"timestamp\\": \\"2025-08-24 20:23:15.957275+00:00\\"}"	\N	2025-08-24 20:23:15.957275+00	48617336
39	2	role_assigned	"{\\"target_user_id\\": 4, \\"old_roles\\": [], \\"new_roles\\": [\\"applicant\\"], \\"assigned_role\\": \\"applicant\\", \\"comment\\": \\"1\\", \\"timestamp\\": \\"2025-08-24 20:23:29.291396+00:00\\"}"	\N	2025-08-24 20:23:29.291396+00	48617336
40	2	user_blocked	"{\\"target_user_id\\": 4, \\"old_status\\": \\"approved\\", \\"new_status\\": \\"blocked\\", \\"reason\\": \\"\\\\u0446\\\\u0443\\", \\"timestamp\\": \\"2025-08-24 20:31:43.179925+00:00\\"}"	\N	2025-08-24 20:31:43.179925+00	48617336
41	2	user_unblocked	"{\\"target_user_id\\": 4, \\"old_status\\": \\"blocked\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"\\\\u0430\\\\u0432\\\\u044b\\", \\"timestamp\\": \\"2025-08-24 20:31:53.995407+00:00\\"}"	\N	2025-08-24 20:31:53.995407+00	48617336
42	2	user_deleted	"{\\"deleted_user_id\\": 4, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": \\"[\\\\\\"applicant\\\\\\"]\\", \\"status\\": \\"approved\\", \\"created_at\\": \\"2025-08-24 20:12:08.486455+00:00\\"}, \\"reason\\": \\"\\\\u044b\\\\u0432\\\\u0430\\\\u044b\\", \\"timestamp\\": \\"2025-08-24 20:32:17.507664+00:00\\"}"	\N	2025-08-24 20:32:17.507664+00	48617336
43	2	user_approved	"{\\"target_user_id\\": 5, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"\\\\u044b\\\\u0432\\\\u0430\\", \\"timestamp\\": \\"2025-08-24 20:34:51.615130+00:00\\"}"	\N	2025-08-24 20:34:51.61513+00	48617336
44	2	user_deleted	"{\\"deleted_user_id\\": 5, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": null, \\"status\\": \\"approved\\", \\"created_at\\": \\"2025-08-24 20:32:31.714523+00:00\\"}, \\"reason\\": \\"\\\\u044b\\\\u0432\\\\u0430\\\\u044b\\\\u0432\\\\u0430\\", \\"timestamp\\": \\"2025-08-24 20:38:30.529023+00:00\\"}"	\N	2025-08-24 20:38:30.529023+00	48617336
45	2	user_approved	"{\\"target_user_id\\": 6, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"123\\", \\"timestamp\\": \\"2025-08-24 20:40:18.488341+00:00\\"}"	\N	2025-08-24 20:40:18.488341+00	48617336
46	2	user_deleted	"{\\"deleted_user_id\\": 6, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": null, \\"status\\": \\"approved\\", \\"created_at\\": \\"2025-08-24 20:39:05.859762+00:00\\"}, \\"reason\\": \\"\\\\u044b\\\\u0432\\\\u0430\\\\u044b\\\\u0432\\", \\"timestamp\\": \\"2025-08-24 20:43:37.863096+00:00\\"}"	\N	2025-08-24 20:43:37.863096+00	48617336
47	2	user_deleted	"{\\"deleted_user_id\\": 7, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": null, \\"status\\": \\"pending\\", \\"created_at\\": \\"2025-08-24 20:46:51.234242+00:00\\"}, \\"reason\\": \\"\\\\u044b\\\\u0432\\\\u0430\\", \\"timestamp\\": \\"2025-08-24 20:47:37.015712+00:00\\"}"	\N	2025-08-24 20:47:37.015712+00	48617336
88	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756113835, \\"nonce\\": \\"KfTpBq6jxXxvOSujbJzX1A\\", \\"specialization\\": \\"security\\"}"	\N	2025-08-25 08:23:55.831375+00	48617336
425	2	shift_ended	{"shift_id": 150, "notes": null}	\N	2025-10-16 17:37:09.334414+00	48617336
48	2	user_deleted	"{\\"deleted_user_id\\": 8, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": null, \\"status\\": \\"pending\\", \\"created_at\\": \\"2025-08-24 20:51:10.216691+00:00\\"}, \\"reason\\": \\"\\\\u0444\\\\u044b\\\\u0432\\", \\"timestamp\\": \\"2025-08-24 20:51:41.086081+00:00\\"}"	\N	2025-08-24 20:51:41.086081+00	48617336
49	2	request_status_changed	{"request_id": 4, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-08-24 20:52:28.316308+00	48617336
73	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756111246, \\"nonce\\": \\"LckBbUUGyYQKjT_h7TmbWg\\", \\"specialization\\": \\"cleaning\\"}"	\N	2025-08-25 07:40:46.106574+00	48617336
75	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756194083, \\"nonce\\": \\"5N-jzHny1UxMVDXbLsvp9Q\\", \\"specialization\\": \\"security\\"}"	\N	2025-08-25 07:41:23.042253+00	48617336
76	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756194083, \\"nonce\\": \\"MRPAzsQpPxiNhqeNfaLylQ\\", \\"specialization\\": \\"security\\"}"	\N	2025-08-25 07:41:23.055524+00	48617336
78	2	user_approved	"{\\"target_user_id\\": 9, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"\\\\u043e\\\\u043a\\", \\"timestamp\\": \\"2025-08-25 07:44:58.466061+00:00\\"}"	\N	2025-08-25 07:44:58.466061+00	48617336
79	2	role_assigned	"{\\"target_user_id\\": 9, \\"old_roles\\": [\\"executor\\"], \\"new_roles\\": [\\"executor\\", \\"applicant\\"], \\"assigned_role\\": \\"applicant\\", \\"comment\\": \\"1\\", \\"timestamp\\": \\"2025-08-25 07:47:54.456270+00:00\\"}"	\N	2025-08-25 07:47:54.45627+00	48617336
80	2	role_removed	"{\\"target_user_id\\": 9, \\"old_roles\\": [\\"executor\\", \\"applicant\\"], \\"new_roles\\": [\\"executor\\"], \\"removed_role\\": \\"applicant\\", \\"comment\\": \\"\\\\u043d\\\\u0435 \\\\u0436\\\\u0438\\\\u0442\\\\u0435\\\\u043b\\\\u044c\\", \\"timestamp\\": \\"2025-08-25 07:50:33.537164+00:00\\"}"	\N	2025-08-25 07:50:33.537164+00	48617336
82	2	role_assigned	"{\\"target_user_id\\": 9, \\"old_roles\\": [\\"executor\\"], \\"new_roles\\": [\\"executor\\", \\"applicant\\"], \\"assigned_role\\": \\"applicant\\", \\"comment\\": \\"\\\\u0432\\\\u044b\\", \\"timestamp\\": \\"2025-08-25 08:06:20.880626+00:00\\"}"	\N	2025-08-25 08:06:20.880626+00	48617336
83	2	role_removed	"{\\"target_user_id\\": 9, \\"old_roles\\": [\\"executor\\", \\"applicant\\"], \\"new_roles\\": [\\"applicant\\"], \\"removed_role\\": \\"executor\\", \\"comment\\": \\"\\\\u0432\\\\u044b\\", \\"timestamp\\": \\"2025-08-25 08:06:20.898084+00:00\\"}"	\N	2025-08-25 08:06:20.898084+00	48617336
74	\N	invite_used	"{\\"nonce\\": \\"LckBbUUGyYQKjT_h7TmbWg\\", \\"role\\": \\"executor\\", \\"created_by\\": 48617336, \\"new_user_id\\": 6055402868, \\"specialization\\": \\"cleaning\\"}"	\N	2025-08-25 07:40:46.111532+00	6055402868
77	\N	invite_used	"{\\"nonce\\": \\"MRPAzsQpPxiNhqeNfaLylQ\\", \\"role\\": \\"executor\\", \\"created_by\\": 48617336, \\"new_user_id\\": 6055402868, \\"specialization\\": \\"security\\"}"	\N	2025-08-25 07:41:36.810967+00	6055402868
89	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756113835, \\"nonce\\": \\"LFrVyv456N3hxXHwXtArbA\\", \\"specialization\\": \\"security\\"}"	\N	2025-08-25 08:23:55.843539+00	48617336
93	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756114559, \\"nonce\\": \\"dT-uXtb7kdJOUOb78EwPHw\\", \\"specialization\\": \\"hvac\\"}"	\N	2025-08-25 08:35:59.594016+00	48617336
94	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756114559, \\"nonce\\": \\"8zg8PhT7K8ligJgOa7DU_w\\", \\"specialization\\": \\"hvac\\"}"	\N	2025-08-25 08:35:59.606426+00	48617336
95	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756117561, \\"nonce\\": \\"7P3ay4SYRCW9j912aq1kRQ\\", \\"specialization\\": \\"maintenance\\"}"	\N	2025-08-25 09:26:01.733374+00	48617336
96	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1756117561, \\"nonce\\": \\"zulg-ubmY-jHXTmZRy6XOg\\", \\"specialization\\": \\"maintenance\\"}"	\N	2025-08-25 09:26:01.747106+00	48617336
106	2	user_approved	"{\\"target_user_id\\": 11, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"\\\\u041e\\\\u0434\\\\u043e\\\\u0431\\\\u0440\\\\u0435\\\\u043d \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u043f\\\\u0430\\\\u043d\\\\u0435\\\\u043b\\\\u044c \\\\u0443\\\\u043f\\\\u0440\\\\u0430\\\\u0432\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u044f \\\\u0441\\\\u043e\\\\u0442\\\\u0440\\\\u0443\\\\u0434\\\\u043d\\\\u0438\\\\u043a\\\\u0430\\\\u043c\\\\u0438\\", \\"timestamp\\": \\"2025-08-25 11:05:06.884608+00:00\\"}"	\N	2025-08-25 11:05:06.884608+00	6055402868
107	2	user_blocked	"{\\"target_user_id\\": 11, \\"old_status\\": \\"approved\\", \\"new_status\\": \\"blocked\\", \\"reason\\": \\"\\\\u0417\\\\u0430\\\\u0431\\\\u043b\\\\u043e\\\\u043a\\\\u0438\\\\u0440\\\\u043e\\\\u0432\\\\u0430\\\\u043d \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u043f\\\\u0430\\\\u043d\\\\u0435\\\\u043b\\\\u044c \\\\u0443\\\\u043f\\\\u0440\\\\u0430\\\\u0432\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u044f \\\\u0441\\\\u043e\\\\u0442\\\\u0440\\\\u0443\\\\u0434\\\\u043d\\\\u0438\\\\u043a\\\\u0430\\\\u043c\\\\u0438\\", \\"timestamp\\": \\"2025-08-25 11:05:22.205166+00:00\\"}"	\N	2025-08-25 11:05:22.205166+00	6055402868
108	2	user_approved	"{\\"target_user_id\\": 11, \\"old_status\\": \\"blocked\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"\\\\u0420\\\\u0430\\\\u0437\\\\u0431\\\\u043b\\\\u043e\\\\u043a\\\\u0438\\\\u0440\\\\u043e\\\\u0432\\\\u0430\\\\u043d \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u043f\\\\u0430\\\\u043d\\\\u0435\\\\u043b\\\\u044c \\\\u0443\\\\u043f\\\\u0440\\\\u0430\\\\u0432\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u044f \\\\u0441\\\\u043e\\\\u0442\\\\u0440\\\\u0443\\\\u0434\\\\u043d\\\\u0438\\\\u043a\\\\u0430\\\\u043c\\\\u0438\\", \\"timestamp\\": \\"2025-08-25 11:05:28.270377+00:00\\"}"	\N	2025-08-25 11:05:28.270377+00	6055402868
115	2	role_assigned	"{\\"target_user_id\\": 2, \\"old_roles\\": [\\"admin\\", \\"executor\\"], \\"new_roles\\": [\\"admin\\", \\"executor\\", \\"applicant\\"], \\"assigned_role\\": \\"applicant\\", \\"comment\\": \\"232\\", \\"timestamp\\": \\"2025-08-25 19:40:14.158995+00:00\\"}"	\N	2025-08-25 19:40:14.158995+00	48617336
116	2	role_assigned	"{\\"target_user_id\\": 2, \\"old_roles\\": [\\"admin\\", \\"executor\\", \\"applicant\\"], \\"new_roles\\": [\\"admin\\", \\"executor\\", \\"applicant\\", \\"manager\\"], \\"assigned_role\\": \\"manager\\", \\"comment\\": \\"232\\", \\"timestamp\\": \\"2025-08-25 19:40:14.176150+00:00\\"}"	\N	2025-08-25 19:40:14.17615+00	48617336
121	2	specialization_change	"{\\"target_user_id\\": 2, \\"old_specializations\\": [\\"electrician\\", \\"repair\\", \\"installation\\"], \\"new_specializations\\": [\\"electrician\\", \\"repair\\", \\"installation\\", \\"maintenance\\", \\"landscaping\\", \\"security\\", \\"hvac\\", \\"plumber\\", \\"cleaning\\"], \\"comment\\": \\"33\\", \\"timestamp\\": \\"2025-08-25T19:59:53.323407\\"}"	\N	2025-08-25 19:59:53.311091+00	48617336
124	2	request_status_changed	{"request_id": 7, "old_status": "\\u041d\\u043e\\u0432\\u0430\\u044f", "new_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "notes": null, "actor_role": "admin"}	\N	2025-08-25 20:33:42.642133+00	48617336
127	2	request_status_changed	{"request_id": 8, "old_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "new_status": "\\u041e\\u0442\\u043c\\u0435\\u043d\\u0435\\u043d\\u0430", "notes": null, "actor_role": "admin"}	\N	2025-08-25 20:36:17.851129+00	48617336
144	2	request_status_changed	{"request_id": 42, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-12 17:28:34.426855+00	48617336
145	2	request_status_changed	{"request_id": 9, "old_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-12 17:29:33.054847+00	6055402868
146	2	request_status_changed	{"request_id": 9, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-12 17:31:07.138456+00	6055402868
147	2	request_status_changed	{"request_id": 42, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-12 17:32:01.590049+00	48617336
148	2	request_status_changed	{"request_id": 8, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-12 17:35:08.90761+00	48617336
149	2	request_status_changed	{"request_id": 15, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-12 17:35:20.424038+00	48617336
150	2	request_status_changed	{"request_id": 8, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-12 17:52:09.92257+00	48617336
151	2	request_status_changed	{"request_id": 4, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-12 18:08:21.159618+00	48617336
152	2	request_status_changed	{"request_id": 15, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-12 18:08:35.754285+00	48617336
153	2	request_status_changed	{"request_id": 15, "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-12 18:11:43.38911+00	48617336
156	2	user_approved	"{\\"target_user_id\\": 12, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"Welcome to test\\", \\"timestamp\\": \\"2025-09-16 19:24:56.096131+00:00\\"}"	\N	2025-09-16 19:24:56.096131+00	61022844
157	2	user_blocked	"{\\"target_user_id\\": 12, \\"old_status\\": \\"approved\\", \\"new_status\\": \\"blocked\\", \\"reason\\": \\"Test\\", \\"timestamp\\": \\"2025-09-16 19:25:31.783109+00:00\\"}"	\N	2025-09-16 19:25:31.783109+00	61022844
158	2	user_deleted	"{\\"deleted_user_id\\": 12, \\"deleted_user_info\\": {\\"telegram_id\\": 61022844, \\"username\\": \\"Nazya_Shlyk\\", \\"first_name\\": \\"Nazya\\", \\"last_name\\": null, \\"role\\": \\"applicant\\", \\"roles\\": null, \\"status\\": \\"blocked\\", \\"created_at\\": \\"2025-09-16 19:05:18.854276+00:00\\"}, \\"reason\\": \\"Test\\", \\"timestamp\\": \\"2025-09-16 19:25:36.764576+00:00\\"}"	\N	2025-09-16 19:25:36.764576+00	61022844
159	2	user_approved	"{\\"target_user_id\\": 13, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"Welcome test\\", \\"timestamp\\": \\"2025-09-16 19:36:39.163279+00:00\\"}"	\N	2025-09-16 19:36:39.163279+00	61022844
160	2	user_approved	"{\\"target_user_id\\": 14, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"\\\\u041f\\\\u0440\\\\u0438\\\\u0432\\\\u0435\\\\u0442\\\\u0441\\\\u0442\\\\u0432\\\\u0443\\\\u044e\\", \\"timestamp\\": \\"2025-09-16 19:52:24.954457+00:00\\"}"	\N	2025-09-16 19:52:24.954457+00	871196710
161	2	role_assigned	"{\\"target_user_id\\": 13, \\"old_roles\\": [], \\"new_roles\\": [\\"manager\\"], \\"assigned_role\\": \\"manager\\", \\"comment\\": \\"\\\\u0422\\\\u0435\\\\u0441\\\\u0442\\\\u043e\\\\u0432\\\\u044b\\\\u0439 \\\\u043c\\\\u0435\\\\u043d\\\\u0435\\\\u0434\\\\u0436\\\\u0435\\\\u0440\\", \\"timestamp\\": \\"2025-09-16 20:00:55.547430+00:00\\"}"	\N	2025-09-16 20:00:55.54743+00	61022844
162	2	request_status_changed	{"request_number": "250917-007", "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-17 19:13:18.802255+00	12345
163	2	request_status_changed	{"request_number": "250917-007", "old_status": "\\u0423\\u0442\\u043e\\u0447\\u043d\\u0435\\u043d\\u0438\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-17 19:14:43.262012+00	12345
164	13	request_status_changed	{"request_number": "250918-001", "old_status": "\\u041d\\u043e\\u0432\\u0430\\u044f", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "applicant"}	\N	2025-09-18 15:53:46.758471+00	61022844
165	2	request_status_changed	{"request_number": "250917-009", "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-19 05:58:57.225647+00	48617336
166	2	request_status_changed	{"request_number": "250917-001", "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-09-20 22:18:15.044528+00	123456789
167	2	user_deleted	"{\\"deleted_user_id\\": 11, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"\\\\u0418\\\\u0432\\\\u0430\\\\u043d\\", \\"last_name\\": \\"\\\\u0418\\\\u0432\\\\u0430\\\\u043d\\\\u043e\\\\u0432\\", \\"role\\": \\"applicant\\", \\"roles\\": \\"[\\\\\\"applicant\\\\\\", \\\\\\"executor\\\\\\"]\\", \\"status\\": \\"approved\\", \\"created_at\\": \\"2025-08-25 08:32:31.731092+00:00\\"}, \\"reason\\": \\"\\\\u0423\\\\u0434\\\\u0430\\\\u043b\\\\u0435\\\\u043d \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u043f\\\\u0430\\\\u043d\\\\u0435\\\\u043b\\\\u044c \\\\u0443\\\\u043f\\\\u0440\\\\u0430\\\\u0432\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u044f \\\\u0441\\\\u043e\\\\u0442\\\\u0440\\\\u0443\\\\u0434\\\\u043d\\\\u0438\\\\u043a\\\\u0430\\\\u043c\\\\u0438\\", \\"timestamp\\": \\"2025-10-12 16:19:12.153153+00:00\\"}"	\N	2025-10-12 16:19:12.153153+00	6055402868
193	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760436682, \\"nonce\\": \\"d3z_kQ571qqV5I4TQvN-tA\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 09:11:22.130027+00	48617336
172	2	user_deleted	"{\\"deleted_user_id\\": 17, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": null, \\"status\\": \\"pending\\", \\"created_at\\": \\"2025-10-12 16:20:42.638322+00:00\\"}, \\"reason\\": \\"1\\", \\"timestamp\\": \\"2025-10-12 17:46:47.062323+00:00\\"}"	\N	2025-10-12 17:46:47.062323+00	6055402868
173	2	user_deleted	"{\\"deleted_user_id\\": 18, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": null, \\"status\\": \\"pending\\", \\"created_at\\": \\"2025-10-12 17:46:59.371351+00:00\\"}, \\"reason\\": \\"1\\", \\"timestamp\\": \\"2025-10-12 17:50:49.745886+00:00\\"}"	\N	2025-10-12 17:50:49.745886+00	6055402868
174	2	user_deleted	"{\\"deleted_user_id\\": 19, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": null, \\"status\\": \\"pending\\", \\"created_at\\": \\"2025-10-12 17:51:00.821616+00:00\\"}, \\"reason\\": \\"1\\", \\"timestamp\\": \\"2025-10-12 17:54:05.682508+00:00\\"}"	\N	2025-10-12 17:54:05.682508+00	6055402868
175	2	user_approved	"{\\"target_user_id\\": 20, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"\\\\u041e\\\\u043a\\", \\"timestamp\\": \\"2025-10-12 17:55:21.084007+00:00\\"}"	\N	2025-10-12 17:55:21.084007+00	6055402868
176	2	request_status_changed	{"request_number": "250917-009", "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-10-12 19:26:36.960012+00	48617336
177	2	request_status_changed	{"request_number": "250917-009", "old_status": "\\u0412 \\u0440\\u0430\\u0431\\u043e\\u0442\\u0435", "new_status": "\\u0417\\u0430\\u043a\\u0443\\u043f", "notes": null, "actor_role": "admin"}	\N	2025-10-13 17:34:16.137015+00	48617336
181	2	user_deleted	"{\\"deleted_user_id\\": 20, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"User\\", \\"last_name\\": \\"User\\", \\"role\\": \\"applicant\\", \\"roles\\": null, \\"status\\": \\"approved\\", \\"created_at\\": \\"2025-10-12 17:54:15.578429+00:00\\"}, \\"reason\\": \\"123\\", \\"timestamp\\": \\"2025-10-14 08:53:01.856043+00:00\\"}"	\N	2025-10-14 08:53:01.856043+00	6055402868
182	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760435703, \\"nonce\\": \\"zDqp5T9sjBarpZ7Yk9RIOA\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 08:55:03.264278+00	48617336
183	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760435703, \\"nonce\\": \\"xyM9iNMIWzF2_PnOsqU0kg\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 08:55:03.273093+00	48617336
184	2	user_deleted	"{\\"deleted_user_id\\": 21, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"\\\\u0418\\\\u0432\\\\u0430\\\\u043d\\\\u043e\\\\u0432\\", \\"last_name\\": \\"\\\\u0418\\\\u0432\\\\u0430\\\\u043d\\", \\"role\\": \\"executor\\", \\"roles\\": null, \\"status\\": \\"pending\\", \\"created_at\\": \\"2025-10-14 08:55:50.467370+00:00\\"}, \\"reason\\": \\"\\\\u0423\\\\u0434\\\\u0430\\\\u043b\\\\u0435\\\\u043d \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u043f\\\\u0430\\\\u043d\\\\u0435\\\\u043b\\\\u044c \\\\u0443\\\\u043f\\\\u0440\\\\u0430\\\\u0432\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u044f \\\\u0441\\\\u043e\\\\u0442\\\\u0440\\\\u0443\\\\u0434\\\\u043d\\\\u0438\\\\u043a\\\\u0430\\\\u043c\\\\u0438\\", \\"timestamp\\": \\"2025-10-14 09:05:02.156231+00:00\\"}"	\N	2025-10-14 09:05:02.156231+00	6055402868
185	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760436320, \\"nonce\\": \\"mUcqTQuzfpxZx2h5IovrDw\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 09:05:20.798841+00	48617336
186	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760436320, \\"nonce\\": \\"3mymgbJGrOJmkKP0xGwsaA\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 09:05:20.808727+00	48617336
187	2	user_blocked	"{\\"target_user_id\\": 22, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"blocked\\", \\"reason\\": \\"\\\\u041e\\\\u0442\\\\u043a\\\\u043b\\\\u043e\\\\u043d\\\\u0435\\\\u043d \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u043f\\\\u0430\\\\u043d\\\\u0435\\\\u043b\\\\u044c \\\\u0443\\\\u043f\\\\u0440\\\\u0430\\\\u0432\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u044f \\\\u0441\\\\u043e\\\\u0442\\\\u0440\\\\u0443\\\\u0434\\\\u043d\\\\u0438\\\\u043a\\\\u0430\\\\u043c\\\\u0438\\", \\"timestamp\\": \\"2025-10-14 09:08:58.453037+00:00\\"}"	\N	2025-10-14 09:08:58.453037+00	6055402868
188	2	user_deleted	"{\\"deleted_user_id\\": 22, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"\\\\u0418\\\\u0432\\\\u0430\\\\u043d\\\\u043e\\\\u0432\\", \\"last_name\\": \\"\\\\u0418\\\\u0432\\\\u0430\\\\u043d\\", \\"role\\": \\"executor\\", \\"roles\\": null, \\"status\\": \\"blocked\\", \\"created_at\\": \\"2025-10-14 09:05:44.780239+00:00\\"}, \\"reason\\": \\"\\\\u0423\\\\u0434\\\\u0430\\\\u043b\\\\u0435\\\\u043d \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u043f\\\\u0430\\\\u043d\\\\u0435\\\\u043b\\\\u044c \\\\u0443\\\\u043f\\\\u0440\\\\u0430\\\\u0432\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u044f \\\\u0441\\\\u043e\\\\u0442\\\\u0440\\\\u0443\\\\u0434\\\\u043d\\\\u0438\\\\u043a\\\\u0430\\\\u043c\\\\u0438\\", \\"timestamp\\": \\"2025-10-14 09:09:00.950067+00:00\\"}"	\N	2025-10-14 09:09:00.950067+00	6055402868
189	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760436553, \\"nonce\\": \\"NduIIziSDMfbYZSnkbg-1w\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 09:09:13.700893+00	48617336
190	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760436553, \\"nonce\\": \\"r7NPUwjRX_aH-VfFKAYZuw\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 09:09:13.708917+00	48617336
191	2	user_blocked	"{\\"target_user_id\\": 23, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"blocked\\", \\"reason\\": \\"\\\\u041e\\\\u0442\\\\u043a\\\\u043b\\\\u043e\\\\u043d\\\\u0435\\\\u043d\\\\u043e \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u0443\\\\u0432\\\\u0435\\\\u0434\\\\u043e\\\\u043c\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u0435 \\\\u043e \\\\u0440\\\\u0435\\\\u0433\\\\u0438\\\\u0441\\\\u0442\\\\u0440\\\\u0430\\\\u0446\\\\u0438\\\\u0438\\", \\"timestamp\\": \\"2025-10-14 09:09:45.343144+00:00\\"}"	\N	2025-10-14 09:09:45.343144+00	6055402868
205	26	shift_started	{"shift_id": 214, "notes": null}	\N	2025-10-14 11:14:50.009746+00	6055402868
192	2	user_deleted	"{\\"deleted_user_id\\": 23, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"\\\\u0438\\\\u0432\\\\u0430\\\\u043d\\\\u043e\\\\u0432\\", \\"last_name\\": \\"\\\\u0418\\\\u0432\\\\u0430\\\\u043d\\", \\"role\\": \\"executor\\", \\"roles\\": null, \\"status\\": \\"blocked\\", \\"created_at\\": \\"2025-10-14 09:09:33.405194+00:00\\"}, \\"reason\\": \\"\\\\u0423\\\\u0434\\\\u0430\\\\u043b\\\\u0435\\\\u043d \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u043f\\\\u0430\\\\u043d\\\\u0435\\\\u043b\\\\u044c \\\\u0443\\\\u043f\\\\u0440\\\\u0430\\\\u0432\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u044f \\\\u0441\\\\u043e\\\\u0442\\\\u0440\\\\u0443\\\\u0434\\\\u043d\\\\u0438\\\\u043a\\\\u0430\\\\u043c\\\\u0438\\", \\"timestamp\\": \\"2025-10-14 09:10:19.269898+00:00\\"}"	\N	2025-10-14 09:10:19.269898+00	6055402868
194	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760436682, \\"nonce\\": \\"548SHi2bZEJivwtyUR_VGA\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 09:11:22.136015+00	48617336
195	2	user_blocked	"{\\"target_user_id\\": 24, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"blocked\\", \\"reason\\": \\"\\\\u041e\\\\u0442\\\\u043a\\\\u043b\\\\u043e\\\\u043d\\\\u0435\\\\u043d\\\\u043e \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u0443\\\\u0432\\\\u0435\\\\u0434\\\\u043e\\\\u043c\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u0435 \\\\u043e \\\\u0440\\\\u0435\\\\u0433\\\\u0438\\\\u0441\\\\u0442\\\\u0440\\\\u0430\\\\u0446\\\\u0438\\\\u0438\\", \\"timestamp\\": \\"2025-10-14 09:18:38.421960+00:00\\"}"	\N	2025-10-14 09:18:38.42196+00	6055402868
196	2	user_deleted	"{\\"deleted_user_id\\": 24, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"\\\\u0418\\\\u0432\\\\u0430\\\\u043d\\\\u043e\\\\u0432\\", \\"last_name\\": \\"\\\\u0418\\\\u0432\\\\u0430\\\\u043d\\", \\"role\\": \\"executor\\", \\"roles\\": null, \\"status\\": \\"blocked\\", \\"created_at\\": \\"2025-10-14 09:16:19.964066+00:00\\"}, \\"reason\\": \\"\\\\u0423\\\\u0434\\\\u0430\\\\u043b\\\\u0435\\\\u043d \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u043f\\\\u0430\\\\u043d\\\\u0435\\\\u043b\\\\u044c \\\\u0443\\\\u043f\\\\u0440\\\\u0430\\\\u0432\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u044f \\\\u0441\\\\u043e\\\\u0442\\\\u0440\\\\u0443\\\\u0434\\\\u043d\\\\u0438\\\\u043a\\\\u0430\\\\u043c\\\\u0438\\", \\"timestamp\\": \\"2025-10-14 09:19:03.276184+00:00\\"}"	\N	2025-10-14 09:19:03.276184+00	6055402868
197	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760437177, \\"nonce\\": \\"WYODIyiT2BitToUBcNONBQ\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 09:19:37.342235+00	48617336
198	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760437177, \\"nonce\\": \\"LKGs9dW0GU2GthtVNaF9tg\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 09:19:37.35128+00	48617336
199	2	user_deleted	"{\\"deleted_user_id\\": 25, \\"deleted_user_info\\": {\\"telegram_id\\": 6055402868, \\"username\\": null, \\"first_name\\": \\"\\\\u0418\\\\u0432\\\\u0430\\\\u043d\\\\u043e\\\\u0432\\", \\"last_name\\": \\"\\\\u0418\\\\u0432\\\\u0430\\\\u043d\\", \\"role\\": \\"executor\\", \\"roles\\": null, \\"status\\": \\"pending\\", \\"created_at\\": \\"2025-10-14 09:19:53.096923+00:00\\"}, \\"reason\\": \\"\\\\u0423\\\\u0434\\\\u0430\\\\u043b\\\\u0435\\\\u043d \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u043f\\\\u0430\\\\u043d\\\\u0435\\\\u043b\\\\u044c \\\\u0443\\\\u043f\\\\u0440\\\\u0430\\\\u0432\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u044f \\\\u0441\\\\u043e\\\\u0442\\\\u0440\\\\u0443\\\\u0434\\\\u043d\\\\u0438\\\\u043a\\\\u0430\\\\u043c\\\\u0438\\", \\"timestamp\\": \\"2025-10-14 09:23:10.011619+00:00\\"}"	\N	2025-10-14 09:23:10.011619+00	6055402868
200	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760437398, \\"nonce\\": \\"3scAdEHo88NF_wgMkkr-GQ\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 09:23:18.953894+00	48617336
201	2	invite_created	"{\\"role\\": \\"executor\\", \\"expires_at\\": 1760437398, \\"nonce\\": \\"hDpPKzl2OtgiHt0opKyXAQ\\", \\"specialization\\": \\"plumber\\"}"	\N	2025-10-14 09:23:18.959127+00	48617336
202	2	user_approved	"{\\"target_user_id\\": 26, \\"old_status\\": \\"pending\\", \\"new_status\\": \\"approved\\", \\"comment\\": \\"\\\\u041e\\\\u0434\\\\u043e\\\\u0431\\\\u0440\\\\u0435\\\\u043d\\\\u043e \\\\u0447\\\\u0435\\\\u0440\\\\u0435\\\\u0437 \\\\u0443\\\\u0432\\\\u0435\\\\u0434\\\\u043e\\\\u043c\\\\u043b\\\\u0435\\\\u043d\\\\u0438\\\\u0435 \\\\u043e \\\\u0440\\\\u0435\\\\u0433\\\\u0438\\\\u0441\\\\u0442\\\\u0440\\\\u0430\\\\u0446\\\\u0438\\\\u0438\\", \\"timestamp\\": \\"2025-10-14 09:23:53.585169+00:00\\"}"	\N	2025-10-14 09:23:53.585169+00	6055402868
203	2	role_change	"{\\"target_user_id\\": 26, \\"old_roles\\": [], \\"new_roles\\": [\\"executor\\"], \\"comment\\": \\"1\\", \\"timestamp\\": \\"2025-10-14T11:14:11.877892\\"}"	\N	2025-10-14 11:14:11.859833+00	6055402868
204	2	specialization_change	"{\\"target_user_id\\": 26, \\"old_specializations\\": [\\"plumber\\"], \\"new_specializations\\": [\\"plumber\\", \\"electrician\\"], \\"comment\\": \\"\\\\u0449\\\\u043b\\", \\"timestamp\\": \\"2025-10-14T11:14:29.980935\\"}"	\N	2025-10-14 11:14:29.96402+00	6055402868
206	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 149, "executor_id": 26, "assignment_score": 0.5, "reasons": ["\\u041d\\u0438\\u0437\\u043a\\u0430\\u044f \\u0442\\u0435\\u043a\\u0443\\u0449\\u0430\\u044f \\u043d\\u0430\\u0433\\u0440\\u0443\\u0437\\u043a\\u0430", "\\u041f\\u043e\\u043b\\u043d\\u0430\\u044f \\u0434\\u043e\\u0441\\u0442\\u0443\\u043f\\u043d\\u043e\\u0441\\u0442\\u044c"], "conflicts": 0}	\N	2025-10-14 18:52:11.709498+00	\N
207	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 153, "executor_id": 26, "assignment_score": 0.48214285714285715, "reasons": ["\\u041d\\u0438\\u0437\\u043a\\u0430\\u044f \\u0442\\u0435\\u043a\\u0443\\u0449\\u0430\\u044f \\u043d\\u0430\\u0433\\u0440\\u0443\\u0437\\u043a\\u0430", "\\u041f\\u043e\\u043b\\u043d\\u0430\\u044f \\u0434\\u043e\\u0441\\u0442\\u0443\\u043f\\u043d\\u043e\\u0441\\u0442\\u044c"], "conflicts": 0}	\N	2025-10-14 18:52:11.769556+00	\N
208	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 158, "executor_id": 26, "assignment_score": 0.43428571428571433, "reasons": ["\\u041d\\u0438\\u0437\\u043a\\u0430\\u044f \\u0442\\u0435\\u043a\\u0443\\u0449\\u0430\\u044f \\u043d\\u0430\\u0433\\u0440\\u0443\\u0437\\u043a\\u0430"], "conflicts": 0}	\N	2025-10-14 18:52:11.779149+00	\N
209	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 163, "executor_id": 26, "assignment_score": 0.43428571428571433, "reasons": ["\\u041d\\u0438\\u0437\\u043a\\u0430\\u044f \\u0442\\u0435\\u043a\\u0443\\u0449\\u0430\\u044f \\u043d\\u0430\\u0433\\u0440\\u0443\\u0437\\u043a\\u0430"], "conflicts": 0}	\N	2025-10-14 18:52:11.796112+00	\N
210	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 168, "executor_id": 26, "assignment_score": 0.4164285714285714, "reasons": ["\\u041d\\u0438\\u0437\\u043a\\u0430\\u044f \\u0442\\u0435\\u043a\\u0443\\u0449\\u0430\\u044f \\u043d\\u0430\\u0433\\u0440\\u0443\\u0437\\u043a\\u0430"], "conflicts": 0}	\N	2025-10-14 18:52:11.812355+00	\N
211	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 174, "executor_id": 26, "assignment_score": 0.3985714285714286, "reasons": ["\\u041d\\u0438\\u0437\\u043a\\u0430\\u044f \\u0442\\u0435\\u043a\\u0443\\u0449\\u0430\\u044f \\u043d\\u0430\\u0433\\u0440\\u0443\\u0437\\u043a\\u0430"], "conflicts": 0}	\N	2025-10-14 18:52:11.831228+00	\N
212	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 178, "executor_id": 26, "assignment_score": 0.41071428571428575, "reasons": ["\\u041f\\u043e\\u043b\\u043d\\u0430\\u044f \\u0434\\u043e\\u0441\\u0442\\u0443\\u043f\\u043d\\u043e\\u0441\\u0442\\u044c"], "conflicts": 0}	\N	2025-10-14 18:52:11.842063+00	\N
213	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 184, "executor_id": 26, "assignment_score": 0.3628571428571429, "reasons": [], "conflicts": 0}	\N	2025-10-14 18:52:11.850389+00	\N
214	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 189, "executor_id": 26, "assignment_score": 0.42857142857142855, "reasons": ["\\u041d\\u0438\\u0437\\u043a\\u0430\\u044f \\u0442\\u0435\\u043a\\u0443\\u0449\\u0430\\u044f \\u043d\\u0430\\u0433\\u0440\\u0443\\u0437\\u043a\\u0430", "\\u041f\\u043e\\u043b\\u043d\\u0430\\u044f \\u0434\\u043e\\u0441\\u0442\\u0443\\u043f\\u043d\\u043e\\u0441\\u0442\\u044c"], "conflicts": 0}	\N	2025-10-14 18:52:11.861476+00	\N
215	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 194, "executor_id": 26, "assignment_score": 0.39285714285714285, "reasons": ["\\u041f\\u043e\\u043b\\u043d\\u0430\\u044f \\u0434\\u043e\\u0441\\u0442\\u0443\\u043f\\u043d\\u043e\\u0441\\u0442\\u044c"], "conflicts": 0}	\N	2025-10-14 18:52:11.891808+00	\N
216	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 198, "executor_id": 26, "assignment_score": 0.37500000000000006, "reasons": ["\\u041f\\u043e\\u043b\\u043d\\u0430\\u044f \\u0434\\u043e\\u0441\\u0442\\u0443\\u043f\\u043d\\u043e\\u0441\\u0442\\u044c"], "conflicts": 0}	\N	2025-10-14 18:52:11.902014+00	\N
217	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 203, "executor_id": 26, "assignment_score": 0.04500000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-14 18:52:11.915488+00	\N
218	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 208, "executor_id": 26, "assignment_score": 0.04500000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-14 18:52:11.927596+00	\N
219	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 61, "successful_assignments": 13, "failed_assignments": 48, "conflicts_found": 28}	\N	2025-10-14 18:52:11.939554+00	\N
220	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 20, "successful_assignments": 0, "failed_assignments": 20, "conflicts_found": 2}	\N	2025-10-14 18:52:33.667924+00	\N
221	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 19:24:00.048917+00	\N
222	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 19:39:00.054239+00	\N
223	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 19:54:00.056057+00	\N
224	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 20:09:00.091021+00	\N
225	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 20:24:00.05979+00	\N
226	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 20:39:00.109738+00	\N
227	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 20:54:00.059899+00	\N
228	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 21:09:00.074662+00	\N
229	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 21:24:00.047403+00	\N
230	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 21:39:00.052556+00	\N
231	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 21:54:00.049233+00	\N
232	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 22:09:00.050982+00	\N
233	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 22:24:00.064729+00	\N
234	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 22:39:00.044171+00	\N
235	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 22:54:00.041318+00	\N
236	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 23:09:00.048339+00	\N
237	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 23:24:00.0422+00	\N
238	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 23:39:00.058989+00	\N
239	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-14 23:54:00.060338+00	\N
240	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 00:09:00.045461+00	\N
241	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 00:24:00.060829+00	\N
242	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 00:39:00.05318+00	\N
243	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 00:54:00.047542+00	\N
244	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 01:09:00.054795+00	\N
245	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 01:24:00.04221+00	\N
246	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 01:39:00.043172+00	\N
247	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 01:54:00.05927+00	\N
248	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 02:09:00.05824+00	\N
249	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 02:24:00.049749+00	\N
250	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 02:39:00.054357+00	\N
251	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 02:54:00.043866+00	\N
252	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 06:54:00.059102+00	\N
253	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 07:09:00.045916+00	\N
254	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 07:24:00.05498+00	\N
255	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 07:39:00.060995+00	\N
256	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 07:54:00.052572+00	\N
257	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 08:09:00.052887+00	\N
258	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 08:24:00.055895+00	\N
259	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 08:39:00.042641+00	\N
260	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 6, "successful_assignments": 0, "failed_assignments": 6, "conflicts_found": 0}	\N	2025-10-15 08:54:00.059837+00	\N
261	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-15 09:09:00.045483+00	\N
262	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-15 09:24:00.056447+00	\N
263	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-15 09:39:00.061192+00	\N
264	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-15 09:54:00.093809+00	\N
265	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-15 10:09:00.094717+00	\N
266	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-15 10:24:00.042163+00	\N
267	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-15 10:39:00.047933+00	\N
268	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-15 10:54:00.082436+00	\N
269	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-16 08:05:34.37125+00	\N
424	2	shift_ended	{"shift_id": 190, "notes": null}	\N	2025-10-16 17:36:52.382814+00	48617336
270	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-16 08:20:02.896917+00	\N
271	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-16 08:20:34.37087+00	\N
272	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-16 08:35:02.888212+00	\N
273	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-16 08:35:34.348008+00	\N
274	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 7, "successful_assignments": 0, "failed_assignments": 7, "conflicts_found": 0}	\N	2025-10-16 08:50:34.346499+00	\N
275	2	role_change	"{\\"target_user_id\\": 2, \\"old_roles\\": [], \\"new_roles\\": [\\"applicant\\", \\"manager\\", \\"executor\\"], \\"comment\\": \\"1\\\\u044a\\", \\"timestamp\\": \\"2025-10-16T09:02:08.096044\\"}"	\N	2025-10-16 09:02:08.070646+00	48617336
276	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 09:05:34.345108+00	\N
277	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 09:20:03.76652+00	\N
278	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 09:20:34.350477+00	\N
279	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 09:35:03.752564+00	\N
280	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 09:35:34.347747+00	\N
281	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 09:50:03.762649+00	\N
282	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 09:50:34.41086+00	\N
283	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 10:05:34.355618+00	\N
284	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 10:20:34.392441+00	\N
285	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 10:35:34.351445+00	\N
286	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 10:50:34.351503+00	\N
287	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 11:05:34.346954+00	\N
288	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 11:20:34.34768+00	\N
289	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 11:25:35.892385+00	\N
290	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 27, "successful_assignments": 0, "failed_assignments": 27, "conflicts_found": 0}	\N	2025-10-16 11:32:34.081122+00	\N
291	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 11:33:27.804354+00	\N
292	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 11, "successful_assignments": 0, "failed_assignments": 11, "conflicts_found": 1}	\N	2025-10-16 11:33:27.85136+00	\N
293	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 11, "successful_assignments": 0, "failed_assignments": 11, "conflicts_found": 1}	\N	2025-10-16 11:33:27.890818+00	\N
294	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 11, "successful_assignments": 0, "failed_assignments": 11, "conflicts_found": 1}	\N	2025-10-16 11:33:27.928623+00	\N
295	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 2, "successful_assignments": 0, "failed_assignments": 2, "conflicts_found": 1}	\N	2025-10-16 11:33:27.959313+00	\N
296	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 11:40:35.956869+00	\N
297	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 43, "successful_assignments": 0, "failed_assignments": 43, "conflicts_found": 4}	\N	2025-10-16 12:02:12.697134+00	\N
298	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 12:05:22.246257+00	\N
299	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3625, "reasons": ["\\u041f\\u043e\\u043b\\u043d\\u0430\\u044f \\u0434\\u043e\\u0441\\u0442\\u0443\\u043f\\u043d\\u043e\\u0441\\u0442\\u044c"], "conflicts": 0}	\N	2025-10-16 12:08:38.598779+00	\N
300	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:38.611346+00	\N
301	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.614359+00	\N
302	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.620438+00	\N
303	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.625939+00	\N
304	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.631453+00	\N
305	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:38.636631+00	\N
306	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:38.642404+00	\N
307	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.643984+00	\N
308	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.649414+00	\N
309	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.655036+00	\N
310	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.660001+00	\N
311	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:38.664967+00	\N
312	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:38.670087+00	\N
313	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.671734+00	\N
314	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.677571+00	\N
315	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.682735+00	\N
316	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.687864+00	\N
317	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:38.69315+00	\N
318	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:38.69849+00	\N
319	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.700095+00	\N
320	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.705293+00	\N
321	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.710375+00	\N
322	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.715772+00	\N
323	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:38.720961+00	\N
324	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:38.726165+00	\N
325	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.727867+00	\N
326	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.73307+00	\N
327	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.738292+00	\N
328	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.743447+00	\N
329	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:38.749365+00	\N
330	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:38.766547+00	\N
331	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.769453+00	\N
332	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.777807+00	\N
333	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.786509+00	\N
334	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.794395+00	\N
335	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:38.802247+00	\N
336	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:38.810188+00	\N
337	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.812851+00	\N
338	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.820729+00	\N
339	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.827391+00	\N
340	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.833011+00	\N
341	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:38.847454+00	\N
342	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:38.852987+00	\N
343	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.854758+00	\N
344	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.860585+00	\N
345	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.925335+00	\N
346	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.931263+00	\N
347	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:38.936736+00	\N
348	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:38.942122+00	\N
349	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.943835+00	\N
350	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.94944+00	\N
351	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.954978+00	\N
352	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.960295+00	\N
353	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:38.965628+00	\N
354	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:38.971021+00	\N
355	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.972794+00	\N
356	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.978103+00	\N
357	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.983275+00	\N
358	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:38.989152+00	\N
359	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:38.994487+00	\N
360	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:39.003491+00	\N
361	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.006972+00	\N
362	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.015289+00	\N
363	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.021831+00	\N
364	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.027365+00	\N
365	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:39.033023+00	\N
366	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:39.038738+00	\N
367	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.04064+00	\N
368	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.045944+00	\N
369	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.051292+00	\N
370	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.057051+00	\N
371	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:39.06248+00	\N
372	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:39.069406+00	\N
373	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.071838+00	\N
374	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.079063+00	\N
375	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.085066+00	\N
376	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.09093+00	\N
377	26	SHIFT_AUTO_ASSIGNED	{"shift_id": null, "executor_id": 26, "assignment_score": 0.3325, "reasons": [], "conflicts": 0}	\N	2025-10-16 12:08:39.09666+00	\N
378	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 1, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 12:08:39.102347+00	\N
379	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.104151+00	\N
380	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.109645+00	\N
381	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.115319+00	\N
382	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 1}	\N	2025-10-16 12:08:39.121181+00	\N
383	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 12:16:07.720361+00	\N
384	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 12:20:22.250213+00	\N
385	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 12:31:07.717135+00	\N
386	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 12:35:22.240237+00	\N
387	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 12:46:07.711962+00	\N
388	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 12:50:22.267187+00	\N
389	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 13:01:07.74003+00	\N
390	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 13:05:22.240094+00	\N
391	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 13:16:07.726622+00	\N
392	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 13:20:22.243945+00	\N
393	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 13:31:07.710089+00	\N
394	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 13:35:22.2433+00	\N
395	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 13:46:07.724262+00	\N
396	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 13:50:22.232624+00	\N
397	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 14:01:07.716385+00	\N
398	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 14:05:22.238232+00	\N
399	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 14:16:07.717755+00	\N
400	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 14:20:22.240507+00	\N
401	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 14:31:07.708926+00	\N
402	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 14:35:22.2316+00	\N
403	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 14:46:07.703766+00	\N
404	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 14:50:22.234925+00	\N
405	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 15:01:07.710701+00	\N
406	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 15:05:22.283266+00	\N
407	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 15:16:07.705581+00	\N
408	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 15:20:22.289263+00	\N
409	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 15:31:07.712085+00	\N
410	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 15:35:22.278155+00	\N
411	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 15:46:07.717653+00	\N
412	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 15:50:22.238615+00	\N
413	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 16:05:22.237578+00	\N
414	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 16:08:54.527707+00	\N
415	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 16:20:22.237134+00	\N
416	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 16:23:54.543017+00	\N
417	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 16:35:22.234888+00	\N
418	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 16:38:54.515576+00	\N
419	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 16:50:22.24433+00	\N
420	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 16:53:54.522365+00	\N
421	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 17:05:22.23734+00	\N
422	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 17:08:54.522572+00	\N
423	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 17:20:22.237507+00	\N
426	2	shift_ended	{"shift_id": 193, "notes": null}	\N	2025-10-16 17:37:13.490472+00	48617336
427	2	shift_ended	{"shift_id": 213, "notes": null}	\N	2025-10-16 17:37:17.12406+00	48617336
428	26	shift_ended	{"shift_id": 214, "notes": null}	\N	2025-10-16 17:37:55.845369+00	6055402868
429	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 17:46:14.670539+00	\N
430	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 8, "successful_assignments": 0, "failed_assignments": 8, "conflicts_found": 0}	\N	2025-10-16 18:01:14.663135+00	\N
431	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 154, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.444781+00	\N
432	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 155, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.484043+00	\N
433	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 156, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.490182+00	\N
434	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 157, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.495952+00	\N
435	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 159, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.500558+00	\N
436	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 160, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.504657+00	\N
437	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 161, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.509087+00	\N
438	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 162, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.513742+00	\N
439	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 164, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.517646+00	\N
440	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 165, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.521437+00	\N
441	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 166, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.525599+00	\N
442	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 167, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.529335+00	\N
443	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 195, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.533238+00	\N
444	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 196, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.53704+00	\N
445	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 197, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.540854+00	\N
446	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 199, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.544594+00	\N
447	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 200, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.548171+00	\N
448	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 201, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.551888+00	\N
449	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 202, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.555747+00	\N
450	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 204, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.559978+00	\N
451	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 205, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.563652+00	\N
452	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 206, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.567571+00	\N
453	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 207, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.571491+00	\N
454	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 209, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.575386+00	\N
455	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 210, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.579075+00	\N
456	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 211, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.582801+00	\N
457	26	SHIFT_AUTO_ASSIGNED	{"shift_id": 212, "executor_id": 26, "assignment_score": 0.04250000000000004, "reasons": ["\\u0415\\u0441\\u0442\\u044c \\u043d\\u0435\\u0437\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043a\\u043e\\u043d\\u0444\\u043b\\u0438\\u043a\\u0442\\u044b"], "conflicts": 0}	\N	2025-10-16 18:33:53.586351+00	\N
458	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 27, "successful_assignments": 27, "failed_assignments": 0, "conflicts_found": 0}	\N	2025-10-16 18:33:53.590209+00	\N
459	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 72, "successful_assignments": 0, "failed_assignments": 72, "conflicts_found": 0}	\N	2025-10-16 18:42:25.32761+00	\N
460	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.631611+00	\N
461	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.657942+00	\N
462	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.663572+00	\N
463	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.67067+00	\N
464	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.675808+00	\N
465	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.680416+00	\N
466	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.684055+00	\N
467	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.687944+00	\N
468	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.692484+00	\N
469	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.696297+00	\N
470	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.699836+00	\N
471	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.703304+00	\N
472	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.707824+00	\N
473	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.71153+00	\N
474	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.715755+00	\N
475	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.719101+00	\N
476	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.72227+00	\N
477	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.725594+00	\N
478	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.728607+00	\N
479	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.731769+00	\N
480	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.734908+00	\N
481	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.738157+00	\N
482	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.741555+00	\N
483	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.744669+00	\N
484	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.747749+00	\N
485	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.750698+00	\N
486	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.753649+00	\N
487	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.756582+00	\N
488	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.759595+00	\N
489	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.763241+00	\N
490	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.766831+00	\N
491	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-16 18:49:57.771082+00	\N
492	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 19, "successful_assignments": 0, "failed_assignments": 19, "conflicts_found": 0}	\N	2025-10-16 18:50:21.60098+00	\N
493	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 18:55:33.293931+00	\N
494	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 19:10:33.296349+00	\N
495	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 19:25:33.30012+00	\N
496	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 19:40:33.299486+00	\N
497	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 19:55:33.284428+00	\N
498	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 20:10:33.286704+00	\N
499	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 20:25:33.283941+00	\N
500	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 20:40:33.369869+00	\N
501	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 20:55:33.288333+00	\N
502	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 21:10:33.297509+00	\N
503	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 21:25:33.279269+00	\N
504	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 21:40:33.299202+00	\N
505	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 21:55:33.28638+00	\N
506	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 22:10:33.282032+00	\N
507	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 22:25:33.281936+00	\N
508	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 22:40:33.291559+00	\N
509	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 22:55:33.282564+00	\N
510	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 23:10:33.30767+00	\N
511	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 23:25:33.289126+00	\N
512	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 23:40:33.327213+00	\N
513	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-16 23:55:33.279615+00	\N
514	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 00:10:33.297523+00	\N
515	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 00:25:33.283255+00	\N
516	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 00:40:33.293854+00	\N
517	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 00:55:33.293628+00	\N
518	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 01:10:33.35002+00	\N
519	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 01:25:33.296852+00	\N
520	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 01:40:33.323213+00	\N
521	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 01:55:33.291138+00	\N
522	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 02:10:33.292162+00	\N
523	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 02:25:33.283715+00	\N
524	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 02:40:33.291013+00	\N
525	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 02:55:33.295152+00	\N
526	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 03:10:33.290097+00	\N
527	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 03:25:33.295618+00	\N
528	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 03:40:33.28371+00	\N
529	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 03:55:33.278619+00	\N
530	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 04:10:33.296449+00	\N
531	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 04:25:33.281765+00	\N
532	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 04:40:33.282097+00	\N
533	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 04:55:33.279293+00	\N
534	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 05:10:33.378572+00	\N
535	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 05:25:33.279517+00	\N
536	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 10:25:33.29017+00	\N
537	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 10:40:33.305093+00	\N
538	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 10:55:33.292263+00	\N
539	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 11:10:33.377619+00	\N
540	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 11:25:33.283087+00	\N
541	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 11:40:33.341435+00	\N
542	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 11:55:33.308699+00	\N
543	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 12:10:33.280215+00	\N
544	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 12:25:33.291178+00	\N
545	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 12:40:33.293497+00	\N
546	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 12:55:33.292834+00	\N
547	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 13:10:33.291745+00	\N
548	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 13:25:33.289679+00	\N
549	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 13:40:33.297249+00	\N
550	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 13:55:33.286496+00	\N
551	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 14:10:33.289468+00	\N
552	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 14:25:33.290621+00	\N
553	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 14:40:33.289616+00	\N
554	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 14:55:33.285634+00	\N
555	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 15:10:33.279729+00	\N
556	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 15:25:33.315935+00	\N
557	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 15:40:33.294468+00	\N
558	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 15:55:33.281678+00	\N
559	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 16:10:33.276824+00	\N
560	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 16:25:33.325181+00	\N
561	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 16:40:33.286564+00	\N
562	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 16:55:33.290342+00	\N
563	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 17:10:33.280414+00	\N
564	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 17:25:33.285862+00	\N
565	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 17:40:33.274692+00	\N
566	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 17:55:33.282318+00	\N
567	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 18:10:33.278696+00	\N
568	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 18:25:33.277067+00	\N
569	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 18:40:33.379641+00	\N
570	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 18:55:33.286636+00	\N
571	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 19:10:33.317363+00	\N
572	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 19:25:33.290811+00	\N
573	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 19:40:33.283786+00	\N
574	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 19:55:33.286566+00	\N
575	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 20:10:33.278676+00	\N
576	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 20:25:33.284515+00	\N
577	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 20:40:33.29355+00	\N
578	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 20:55:33.277366+00	\N
579	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 21:10:33.292621+00	\N
580	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 21:25:33.29467+00	\N
581	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 21:40:33.301595+00	\N
582	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 21:55:33.293502+00	\N
583	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 22:10:33.297521+00	\N
584	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 22:25:33.294882+00	\N
585	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 22:40:33.293354+00	\N
586	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 22:55:33.286072+00	\N
587	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 23:10:33.279718+00	\N
588	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 23:25:33.294081+00	\N
589	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 23:40:33.3307+00	\N
590	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-17 23:55:33.289046+00	\N
591	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 00:10:33.320094+00	\N
592	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 00:25:33.287181+00	\N
593	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 00:40:33.275262+00	\N
594	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 00:55:33.295238+00	\N
595	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 01:10:33.280778+00	\N
596	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 01:25:33.289355+00	\N
597	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 01:40:33.287743+00	\N
598	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 01:55:33.28098+00	\N
599	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 02:10:33.278288+00	\N
600	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 02:25:33.285835+00	\N
601	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 02:40:33.346015+00	\N
602	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 02:55:33.306761+00	\N
603	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 03:10:33.303072+00	\N
604	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 03:25:33.278102+00	\N
605	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 03:40:33.278253+00	\N
606	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 03:55:33.284183+00	\N
607	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 04:10:33.285688+00	\N
608	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 04:25:33.277979+00	\N
609	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 04:40:33.293872+00	\N
610	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 04:55:33.288425+00	\N
611	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 05:10:33.297334+00	\N
612	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 05:25:33.294001+00	\N
613	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 05:40:33.359846+00	\N
614	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 05:55:33.290542+00	\N
615	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 06:10:33.329812+00	\N
616	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 06:25:33.288445+00	\N
617	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 07:10:33.300315+00	\N
618	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 07:25:33.329201+00	\N
619	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 07:40:33.310767+00	\N
620	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 07:55:33.284957+00	\N
621	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 08:10:33.281994+00	\N
622	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 08:25:33.292152+00	\N
623	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 08:40:33.304013+00	\N
624	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-18 08:55:33.291436+00	\N
625	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 09:10:33.323527+00	\N
626	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 09:25:33.282676+00	\N
627	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 09:40:33.297908+00	\N
628	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 09:55:33.288484+00	\N
629	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 10:10:33.277694+00	\N
630	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 10:25:33.301067+00	\N
631	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 10:40:33.276301+00	\N
632	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 10:55:33.277906+00	\N
633	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 11:10:33.301726+00	\N
634	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 11:25:33.289188+00	\N
635	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 11:40:33.28148+00	\N
636	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 11:55:33.284927+00	\N
637	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 12:10:33.296752+00	\N
638	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 12:25:33.279534+00	\N
639	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 12:40:33.279921+00	\N
640	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 12:55:33.298113+00	\N
641	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 13:10:33.29779+00	\N
642	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 13:25:33.311341+00	\N
643	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 13:40:33.391096+00	\N
644	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 13:55:33.306542+00	\N
645	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 14:10:33.289896+00	\N
646	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 14:25:33.297311+00	\N
647	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 14:40:33.311707+00	\N
648	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 14:55:33.287675+00	\N
649	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 15:10:33.295178+00	\N
650	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 15:25:33.283016+00	\N
651	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 15:40:33.3789+00	\N
652	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 15:55:33.283757+00	\N
653	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 16:10:33.301265+00	\N
654	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 16:25:33.318824+00	\N
655	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 16:40:33.286962+00	\N
656	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 16:55:33.293226+00	\N
657	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 17:10:33.305056+00	\N
658	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 17:25:33.292908+00	\N
659	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 17:40:33.310227+00	\N
660	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 17:55:33.294504+00	\N
661	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 18:10:33.299961+00	\N
662	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 18:25:33.297905+00	\N
663	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 18:40:33.315388+00	\N
664	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 18:55:33.289469+00	\N
665	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 19:10:33.28622+00	\N
666	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 19:25:33.295188+00	\N
667	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 19:40:33.287543+00	\N
668	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 19:55:33.295269+00	\N
669	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 20:10:33.283391+00	\N
670	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 20:25:33.290816+00	\N
671	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 20:40:33.296242+00	\N
672	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 20:55:33.288272+00	\N
673	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 21:10:33.28538+00	\N
674	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 21:25:33.283049+00	\N
675	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 21:40:33.293827+00	\N
676	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 21:55:33.307124+00	\N
677	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 22:10:33.280132+00	\N
678	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 22:55:33.295449+00	\N
679	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 23:10:33.288906+00	\N
680	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 23:25:33.287042+00	\N
681	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 23:40:33.337439+00	\N
682	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-18 23:55:33.334992+00	\N
683	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 00:10:33.359367+00	\N
684	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 00:25:33.289253+00	\N
685	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-19 00:30:00.050211+00	\N
686	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-19 00:30:00.115499+00	\N
687	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-19 00:30:00.121072+00	\N
688	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-19 00:30:00.125163+00	\N
689	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-19 00:30:00.128641+00	\N
690	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 00:40:33.293905+00	\N
691	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 00:55:33.287012+00	\N
692	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 01:10:33.285074+00	\N
693	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 01:25:33.284398+00	\N
694	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 01:40:33.293231+00	\N
695	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 01:55:33.291281+00	\N
696	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 02:10:33.290227+00	\N
697	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 02:25:33.285352+00	\N
698	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 02:40:33.285352+00	\N
699	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 02:55:33.285915+00	\N
700	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 03:10:33.28595+00	\N
701	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 03:25:33.283249+00	\N
702	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 03:40:33.366633+00	\N
703	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 03:55:33.286365+00	\N
704	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 04:10:33.286095+00	\N
705	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 04:25:33.282152+00	\N
706	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 04:40:33.28264+00	\N
707	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 04:55:33.279397+00	\N
708	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 05:10:33.287125+00	\N
709	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 05:25:33.284035+00	\N
710	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 05:40:33.295995+00	\N
711	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 05:55:33.289306+00	\N
712	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 06:10:33.289437+00	\N
713	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 06:25:33.290372+00	\N
714	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 06:40:33.288183+00	\N
715	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 06:55:33.284051+00	\N
716	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 07:10:33.291317+00	\N
717	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 07:25:33.303161+00	\N
718	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 07:40:33.322781+00	\N
719	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 07:55:33.285559+00	\N
720	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 08:10:33.30623+00	\N
721	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 08:25:33.310029+00	\N
722	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 08:40:33.333056+00	\N
723	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-19 08:55:33.291239+00	\N
724	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 09:10:33.300138+00	\N
725	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 09:25:33.285325+00	\N
726	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 09:40:33.296892+00	\N
727	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 09:55:33.297372+00	\N
728	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 10:10:33.293805+00	\N
729	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 10:25:33.290083+00	\N
730	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 10:40:33.334916+00	\N
731	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 10:55:33.296749+00	\N
732	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 11:10:33.303913+00	\N
733	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 11:25:33.29375+00	\N
734	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 11:40:33.277019+00	\N
735	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 11:55:33.285677+00	\N
736	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 12:10:33.284256+00	\N
737	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 12:25:33.284081+00	\N
738	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 12:40:33.281595+00	\N
739	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 12:55:33.28074+00	\N
740	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 13:10:33.287317+00	\N
741	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 13:25:33.294156+00	\N
742	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 13:40:33.302072+00	\N
743	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 13:55:33.297985+00	\N
744	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 14:10:33.280832+00	\N
745	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 14:25:33.275202+00	\N
746	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 14:40:33.285973+00	\N
747	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 14:55:33.289435+00	\N
748	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 15:10:33.289219+00	\N
749	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 15:25:33.380037+00	\N
750	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 15:40:33.29642+00	\N
751	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 15:55:33.318744+00	\N
752	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 16:10:33.28683+00	\N
753	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 16:25:33.281696+00	\N
754	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 16:40:33.282251+00	\N
755	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 16:55:33.287863+00	\N
756	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 17:10:33.278268+00	\N
757	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 17:25:33.285971+00	\N
758	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 17:40:33.295308+00	\N
759	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 17:55:33.29736+00	\N
760	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 18:10:33.288347+00	\N
761	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 18:25:33.278781+00	\N
762	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 18:40:33.299465+00	\N
763	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 18:55:33.301267+00	\N
764	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 19:10:33.297409+00	\N
765	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 19:25:33.278668+00	\N
766	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 19:40:33.352097+00	\N
767	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 19:55:33.281049+00	\N
768	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 20:10:33.354816+00	\N
769	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 20:25:33.325956+00	\N
770	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 20:40:33.303659+00	\N
771	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 20:55:33.301625+00	\N
772	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 21:10:33.304599+00	\N
773	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 21:25:33.301903+00	\N
774	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 21:40:33.306586+00	\N
775	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 21:55:33.297411+00	\N
776	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 22:10:33.2784+00	\N
777	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 22:25:33.289741+00	\N
778	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 22:40:33.292067+00	\N
779	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 22:55:33.298582+00	\N
780	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 23:10:33.298707+00	\N
781	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 23:25:33.279289+00	\N
782	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 23:40:33.279818+00	\N
783	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-19 23:55:33.277236+00	\N
784	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 00:10:33.292678+00	\N
785	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 00:25:33.28184+00	\N
786	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 00:30:00.03296+00	\N
787	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 00:30:00.104678+00	\N
788	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 00:30:00.109931+00	\N
789	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 00:30:00.113195+00	\N
790	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 00:30:00.116719+00	\N
791	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 00:40:33.284025+00	\N
792	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 00:55:33.283994+00	\N
793	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 01:10:33.286677+00	\N
794	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 01:25:33.288052+00	\N
795	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 01:40:33.278973+00	\N
796	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 01:55:33.291325+00	\N
797	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 02:10:33.342043+00	\N
798	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 02:25:33.290036+00	\N
799	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 02:40:33.317048+00	\N
800	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 02:55:33.287688+00	\N
801	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 03:10:33.32694+00	\N
802	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 03:25:33.316277+00	\N
803	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 03:40:33.28788+00	\N
804	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 03:55:33.327865+00	\N
805	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 04:10:33.285175+00	\N
806	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 04:25:33.305622+00	\N
807	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 04:40:33.299065+00	\N
808	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 04:55:33.292592+00	\N
809	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 05:10:33.305555+00	\N
810	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 05:25:33.279898+00	\N
811	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 05:40:33.303079+00	\N
812	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 05:55:33.288194+00	\N
813	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 06:10:33.288439+00	\N
814	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 06:25:33.275213+00	\N
815	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 06:40:33.279248+00	\N
816	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 06:55:33.281039+00	\N
817	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 07:10:33.320703+00	\N
818	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 07:25:33.292893+00	\N
819	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 07:40:33.316102+00	\N
820	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 07:55:33.296288+00	\N
821	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.107866+00	\N
822	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.199621+00	\N
823	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.204781+00	\N
824	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.209205+00	\N
825	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.213619+00	\N
826	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.21869+00	\N
827	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.222638+00	\N
828	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.227059+00	\N
829	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.230938+00	\N
830	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.23537+00	\N
831	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.239372+00	\N
832	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.24459+00	\N
833	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.248406+00	\N
834	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.252403+00	\N
835	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.2625+00	\N
836	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.268457+00	\N
837	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.27445+00	\N
838	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.279785+00	\N
839	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.284283+00	\N
840	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.291493+00	\N
841	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.296346+00	\N
842	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.302787+00	\N
843	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.30758+00	\N
844	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.311307+00	\N
845	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.314801+00	\N
846	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.319762+00	\N
847	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.323883+00	\N
848	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.328383+00	\N
849	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.332332+00	\N
850	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.336137+00	\N
851	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.340157+00	\N
852	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.344514+00	\N
853	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.348869+00	\N
854	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.353751+00	\N
855	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 1, "successful_assignments": 0, "failed_assignments": 1, "conflicts_found": 0}	\N	2025-10-20 08:00:00.35884+00	\N
856	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 08:10:33.283135+00	\N
857	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 08:25:33.307811+00	\N
858	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 08:40:33.288992+00	\N
859	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 10, "successful_assignments": 0, "failed_assignments": 10, "conflicts_found": 0}	\N	2025-10-20 08:55:33.285482+00	\N
860	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 09:10:33.324813+00	\N
861	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 09:25:33.284922+00	\N
862	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 09:40:33.296532+00	\N
863	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 09:55:33.275228+00	\N
864	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 10:10:33.290662+00	\N
865	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 10:25:33.29548+00	\N
866	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 10:40:33.295122+00	\N
867	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 10:55:33.296857+00	\N
868	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 11:10:33.285387+00	\N
869	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 11:25:33.284265+00	\N
870	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 11:40:33.286809+00	\N
871	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 11:55:33.305874+00	\N
872	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 12:10:33.310379+00	\N
873	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 12:25:33.285394+00	\N
874	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 12:55:33.842542+00	\N
875	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 13:10:33.370528+00	\N
876	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 13:25:33.281971+00	\N
877	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 13:40:33.27973+00	\N
878	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 13:55:33.292784+00	\N
879	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 14:10:33.286642+00	\N
880	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 14:25:33.278526+00	\N
881	\N	BATCH_ASSIGNMENT_COMPLETED	{"total_shifts": 5, "successful_assignments": 0, "failed_assignments": 5, "conflicts_found": 0}	\N	2025-10-20 14:40:33.297432+00	\N
\.


--
-- Data for Name: buildings; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.buildings (id, address, yard_id, gps_latitude, gps_longitude, entrance_count, floor_count, description, is_active, created_at, created_by, updated_at) FROM stdin;
1	Yangi Olmazor, 14V	1	41.349151	69.246436	2	9	\N	t	2025-10-12 15:28:07.736307+00	2	\N
2	Yangi Olmazor, 13V	1	41.349049	69.247218	2	9	\N	t	2025-10-12 19:24:01.154598+00	2	\N
3	Yangi Olmazor, 12V	1	41.349726	69.247271	1	12	\N	t	2025-10-12 19:25:43.485153+00	2	\N
\.


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.notifications (id, user_id, notification_type, title, content, is_read, is_sent, meta_data, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: planning_conflicts; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.planning_conflicts (id, quarterly_plan_id, conflict_type, status, involved_schedule_ids, involved_user_ids, conflict_time, conflict_date, conflict_details, description, suggested_resolutions, applied_resolution, resolved_at, resolved_by, priority, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: quarterly_plans; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.quarterly_plans (id, year, quarter, start_date, end_date, created_by, status, specializations, coverage_24_7, load_balancing_enabled, auto_transfers_enabled, notifications_enabled, total_shifts_planned, total_hours_planned, coverage_percentage, total_conflicts, resolved_conflicts, pending_conflicts, settings, notes, created_at, updated_at, activated_at, archived_at) FROM stdin;
\.


--
-- Data for Name: quarterly_shift_schedules; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.quarterly_shift_schedules (id, quarterly_plan_id, planned_date, planned_start_time, planned_end_time, assigned_user_id, specialization, schedule_type, status, actual_shift_id, shift_config, coverage_areas, priority, notes, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: ratings; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.ratings (id, request_number, user_id, rating, review, created_at) FROM stdin;
2	251012-001	2	1	\N	2025-10-13 17:22:37.977779+00
3	251013-001	2	5	\N	2025-10-13 19:07:45.801094+00
4	250917-009	2	5	\N	2025-10-13 19:27:34.523541+00
5	250920-001	2	5	\N	2025-10-13 19:27:40.066232+00
6	250917-002	2	5	\N	2025-10-14 11:37:19.627029+00
7	251016-010	2	5	\N	2025-10-16 11:53:15.41631+00
8	251016-009	2	4	\N	2025-10-16 17:32:12.945321+00
\.


--
-- Data for Name: request_assignments; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.request_assignments (id, request_number, assignment_type, group_specialization, executor_id, status, created_at, created_by) FROM stdin;
1	250917-005	group	plumber	\N	active	2025-09-17 08:40:19.40221+00	2
2	250917-004	group	plumber	\N	active	2025-09-17 08:40:54.071648+00	2
3	250917-002	group	plumber	\N	active	2025-09-17 08:41:08.750951+00	2
4	250917-007	group	plumber	\N	active	2025-09-17 18:29:14.564295+00	2
5	250917-008	group	plumber	\N	active	2025-09-17 19:26:16.064935+00	2
6	250917-001	group	plumber	\N	active	2025-09-17 19:39:28.232292+00	2
7	251013-001	group	electrician	\N	active	2025-10-13 18:17:31.764595+00	2
8	250917-009	group	electrician	\N	active	2025-10-13 18:17:31.764595+00	2
9	250920-001	group	electrician	\N	active	2025-10-13 18:17:31.764595+00	2
10	251012-001	individual	\N	2	active	2025-10-13 18:20:36.141734+00	2
13	251016-009	individual	\N	2	active	2025-10-16 10:24:14.092405+00	2
15	251016-010	group	electrician	\N	active	2025-10-16 10:24:34.883007+00	2
16	251016-005	individual	\N	2	cancelled	2025-10-16 10:56:11.856869+00	2
17	251016-005	individual	\N	2	cancelled	2025-10-16 11:03:42.443598+00	2
18	251016-005	individual	\N	2	active	2025-10-16 11:15:58.051715+00	2
14	251016-006	individual	\N	26	cancelled	2025-10-16 10:24:23.135475+00	2
19	251016-006	individual	\N	2	cancelled	2025-10-16 11:16:06.451738+00	2
20	251016-006	individual	\N	26	active	2025-10-16 11:28:19.563769+00	2
12	251016-007	group	hvac	\N	cancelled	2025-10-16 10:03:15.989437+00	13
21	251016-007	individual	\N	2	active	2025-10-16 17:32:39.627478+00	2
\.


--
-- Data for Name: request_comments; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.request_comments (id, request_number, user_id, comment_text, comment_type, previous_status, new_status, created_at) FROM stdin;
1	250917-007	16	Необходимо закупить материалы:\nТрубы - 5 метров\nФитинги - 10 штук\nКлей - 1 тюбик	purchase	\N	\N	2025-09-17 15:33:43.809388+00
2	250917-008	16	Необходимо закупить материалы:\nТрубы - 5 метров\nФитинги - 10 штук\nКлей - 1 тюбик	purchase	\N	\N	2025-09-17 15:33:56.490084+00
3	250917-007	2	Необходимо закупить материалы:\nПослала	purchase	\N	\N	2025-09-17 19:14:43.268886+00
5	250917-009	2	Необходимо закупить материалы:\nПровода	purchase	\N	\N	2025-09-19 05:58:57.233464+00
6	250917-001	2	Необходимо закупить материалы:\nПровода	purchase	\N	\N	2025-09-20 22:18:15.060569+00
7	250917-009	2	Необходимо закупить материалы:\nТрубы провода	purchase	\N	\N	2025-10-12 19:26:36.966214+00
8	250917-009	2	Необходимо закупить материалы:\nываываыва	purchase	\N	\N	2025-10-13 17:34:16.147361+00
\.


--
-- Data for Name: requests; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.requests (request_number, user_id, category, status, address, description, apartment, urgency, media_files, executor_id, notes, completion_report, completion_media, assignment_type, assigned_group, assigned_at, assigned_by, purchase_materials, requested_materials, manager_materials_comment, purchase_history, created_at, updated_at, completed_at, apartment_id, is_returned, return_reason, return_media, returned_at, returned_by, manager_confirmed, manager_confirmed_by, manager_confirmed_at, manager_confirmation_notes) FROM stdin;
250917-004	2	Сантехника	Отменена	Олмазор сити, 14, 55	Dhdjudisjsjsjsjs	\N	Критическая	[]	\N	\n\nОтклонена менеджером Andrey 17.09.2025 15:29	\N	[]	group	plumber	2025-09-17 08:40:54.079172+00	2	\N	\N	\N	\N	2025-09-17 08:10:54.345102+00	2025-09-17 15:29:58.494198+00	\N	\N	f	\N	\N	\N	\N	f	\N	\N	\N
250917-005	2	Сантехника	Отменена	Олмазор сити, 14, 55	Cbshsikskakaksksks	\N	Критическая	[]	\N	\n\nОтклонена менеджером Andrey 17.09.2025 18:28	\N	[]	group	plumber	2025-09-17 08:40:19.412267+00	2	\N	\N	\N	\N	2025-09-17 08:20:25.642677+00	2025-09-17 18:28:13.861824+00	\N	\N	f	\N	\N	\N	\N	f	\N	\N	\N
250917-006	16	Сантехника	Отменена	Тестовая улица, 1	Тестовая заявка для проверки закупа	\N	Обычная	[]	\N	--- УТОЧНЕНИЕ 17.09.2025 19:02 ---\n👨‍💼 Andrey Afanasyev:\nChuff\n\nОтклонена менеджером Andrey Afanasyev 17.09.2025 19:03\nПричина: Hcycucucuc	\N	[]	\N	\N	\N	\N	\N	\N	\N	\N	2025-09-17 15:33:24.373992+00	2025-09-17 19:11:57.760177+00	\N	\N	f	\N	\N	\N	\N	f	\N	\N	\N
251013-001	2	Электрика	Принято	Квартира 1, Yangi Olmazor, 14V, (Фаза 1 (ЛОТ 4))	ываывафыва	\N	Срочная	[]	\N	\n[Исполнитель] Работа выполнена: сделано	\N	"[{\\"type\\": \\"photo\\", \\"file_id\\": \\"AgACAgIAAxkBAAInsGjtSZE_MDisnjfSSLN-aWzHAibkAAJeCDIb58xoS-M95yxL0IvKAQADAgADeAADNgQ\\"}]"	\N	\N	\N	\N	\N	\N	\N	\N	2025-10-13 07:52:57.06897+00	2025-10-13 19:07:45.801094+00	2025-10-13 19:07:45.808753+00	1	f	\N	\N	\N	\N	t	2	2025-10-13 19:06:49.19478+00	\N
250917-002	2	Сантехника	Принято	Тестовый адрес	Тестовая заявка для проверки системы нумерации	123	Обычная	["AgACAgIAAxkBAAEDCcZo7fy05G-HgQdgB7aBqHOwJ6HNJgACgfcxG_caUEuElmvPV2DJqQEAAwIAA3kAAzYE"]	\N	\n[Исполнитель] Работа выполнена: сделано	\N	"[{\\"type\\": \\"photo\\", \\"file_id\\": \\"AgACAgIAAxkBAAIqL2juNaDwXCtTYrQ-5C2DH1Q1MQEVAALN9jEbXeVwS9WA0UixqY80AQADAgADeAADNgQ\\"}]"	group	plumber	2025-09-17 08:41:08.75892+00	2	\N	\N	\N	\N	2025-09-17 08:08:47.45687+00	2025-10-14 11:37:19.627029+00	2025-10-14 11:37:19.639474+00	\N	f	не сделано ничего	[]	2025-10-13 16:40:07.007393+00	2	t	2	2025-10-14 11:36:57.784893+00	\N
250917-009	2	Электрика	Принято	Олмазор сити, 14, 55	Аововлвдыжыжыжы	\N	Критическая	[]	2	--- УТОЧНЕНИЕ 17.09.2025 19:28 ---\n👨‍💼 Andrey Afanasyev:\nЧто случилось\n[Пользователь] Уточнение: Нет воды\n[Исполнитель] Работа выполнена: сделано\n[Исполнитель] Работа выполнена: None	\N	"[{\\"type\\": \\"photo\\", \\"file_id\\": \\"AgACAgIAAxkBAAIodWjtUnmHbKvuIivsvntNMazA-lO-AAKQCDIb58xoS74_PBZBYTeIAQADAgADeQADNgQ\\"}]"	manual	\N	\N	\N	ываываыва	Провода\nТрубы провода\nываываыва	Какие трубы	Запрошенные материалы: Провода\nТрубы провода\nКомментарий менеджера: Какие трубы\nОбновлено: 12.10.2025 19:26	2025-09-17 19:28:11.977499+00	2025-10-13 19:27:34.523541+00	2025-10-13 19:27:34.535309+00	\N	f	\N	\N	\N	\N	t	2	2025-10-13 19:27:23.391096+00	\N
250917-007	16	Сантехника	Принято	Тестовая улица, 1	Тестовая заявка для проверки закупа	\N	Обычная	[]	\N	--- УТОЧНЕНИЕ 17.09.2025 19:14 ---\n👨‍💼 Andrey Afanasyev:\nТолько\n\n--- УТОЧНЕНИЕ 17.09.2025 19:15 ---\n👨‍💼 Andrey Afanasyev:\nПослала\n\n--- УТОЧНЕНИЕ 17.09.2025 19:26 ---\n👨‍💼 Andrey Afanasyev:\nАталалвдвдвдвв	\N	[]	group	plumber	2025-09-17 18:29:14.570718+00	2	Послала	Послал Влад\nПослала	\N	\N	2025-09-17 15:33:43.80265+00	2025-10-14 12:03:52.138951+00	2025-10-13 09:31:11.818386+00	\N	f	\N	\N	\N	\N	t	2	2025-10-14 12:03:52.14905+00	\n\n--- ПРИНЯТО МЕНЕДЖЕРОМ 14.10.2025 12:03 ---\n👨‍💼 Менеджер: Andrey Afanasyev\n💬 Комментарий: принятие заявки\n⚠️ Заявка принята без оценки заявителя
251012-001	2	Электрика	Принято	Олмазор сити, 14, 55	sfasdfsafsfasfdasf	\N	Критическая	[]	\N	\N	\N	[]	\N	\N	\N	\N	\N	\N	\N	\N	2025-10-12 10:02:18.805834+00	2025-10-13 17:22:37.977779+00	2025-10-13 17:22:37.984993+00	\N	f	\N	\N	\N	\N	f	\N	\N	\N
250920-001	2	Электрика	Принято	Олмазор сити, 14, 55	Сбой родичи	\N	Срочная	[]	\N	--- УТОЧНЕНИЕ 20.09.2025 22:38 ---\n👨‍💼 Andrey Afanasyev:\nСбой чего?\n[Пользователь] Уточнение: Электрики\n[Пользователь] Уточнение: 234234\n[Пользователь] Уточнение: Не работают\n[Исполнитель] Работа выполнена: 	\N	[]	\N	\N	\N	\N	\N	\N	\N	\N	2025-09-20 22:37:29.232108+00	2025-10-13 19:27:40.066232+00	2025-10-13 19:27:40.075167+00	\N	f	\N	\N	\N	\N	f	\N	\N	\N
250917-001	15	Сантехника	Принято	ул. Тестовая, д. 1	Течет кран в ванной комнате	15	Обычная	[]	\N	--- УТОЧНЕНИЕ 17.09.2025 19:27 ---\n👨‍💼 Andrey Afanasyev:\nЗачем	\N	[]	group	plumber	2025-09-17 19:39:28.245128+00	2	Провода	Провода\n--закуплено 12.10.2025 19:27--\n	\N	ЗАКУП ЗАВЕРШЕН:\nМатериалы: Провода\nКомментарий менеджера: Без комментариев\nДата завершения: 12.10.2025 19:27	2025-09-17 08:04:48.160637+00	2025-10-14 12:03:27.588371+00	2025-10-13 16:47:42.596023+00	\N	f	\N	\N	\N	\N	t	2	2025-10-14 12:03:27.597554+00	\n\n--- ПРИНЯТО МЕНЕДЖЕРОМ 14.10.2025 12:03 ---\n👨‍💼 Менеджер: Andrey Afanasyev\n💬 Комментарий: не отвечает\n⚠️ Заявка принята без оценки заявителя
250917-008	16	Сантехника	Принято	Тестовая улица, 1	Тестовая заявка для проверки закупа	\N	Обычная	[]	\N	--- УТОЧНЕНИЕ 17.09.2025 19:09 ---\n👨‍💼 Andrey Afanasyev:\nПоплакала\n\n--- УТОЧНЕНИЕ 17.09.2025 19:23 ---\n👨‍💼 Andrey Afanasyev:\nПоплакала\n\n--- УТОЧНЕНИЕ 17.09.2025 19:26 ---\n👨‍💼 Andrey Afanasyev:\nЛпаладвжв\n[Исполнитель] Требуется закуп: трубы нужны\n[Исполнитель] Работа выполнена: сделано\n[Исполнитель] Работа выполнена: 	\N	"[{\\"type\\": \\"photo\\", \\"file_id\\": \\"AgACAgIAAxkBAAIqKGjuMnQ7M_tpMhfUPW-O0CITKWmNAAKu9jEbXeVwS1enOupY0p8TAQADAgADeAADNgQ\\"}]"	group	plumber	2025-09-17 19:26:16.075032+00	2	\N	\N	Закуплено	Запрошенные материалы: Не указано\nКомментарий менеджера: Закуплено\nОбновлено: 17.09.2025 19:08	2025-09-17 15:33:56.478313+00	2025-10-14 12:04:09.901845+00	\N	\N	f	\N	\N	\N	\N	t	2	2025-10-14 12:04:09.912277+00	\n\n--- ПРИНЯТО МЕНЕДЖЕРОМ 14.10.2025 12:04 ---\n👨‍💼 Менеджер: Andrey Afanasyev\n💬 Комментарий: принятие заявки\n⚠️ Заявка принята без оценки заявителя
251016-008	2	Благоустройство	Новая	Двор: Фаза 1 (ЛОТ 4)	тестовая заявка 7	\N	Средняя	[]	\N	\N	\N	[]	\N	\N	\N	\N	\N	\N	\N	\N	2025-10-16 08:49:40.243119+00	\N	\N	\N	f	\N	[]	\N	\N	f	\N	\N	\N
251016-001	2	Электрика	Отменена	Квартира 1, Yangi Olmazor, 14V, (Фаза 1 (ЛОТ 4))	тестовая заявка 5	\N	Срочная	["AgACAgIAAxkBAAIsN2jv-dwIzXXif8jkJJAlu1p9Sz_bAAKKAzIbLCt5S5XezEtAVjNGAQADAgADeAADNgQ"]	\N	Отклонена менеджером Andrey Afanasyev 16.10.2025 08:57\nПричина: 234234	\N	[]	\N	\N	\N	\N	\N	\N	\N	\N	2025-10-16 08:34:07.612286+00	2025-10-16 08:57:39.411991+00	\N	1	f	\N	[]	\N	\N	f	\N	\N	\N
251016-002	2	Электрика	Отменена	Квартира 1, Yangi Olmazor, 14V, (Фаза 1 (ЛОТ 4))	тестовая заявка 5	\N	Срочная	[]	\N	Отклонена менеджером Andrey Afanasyev 16.10.2025 08:57\nПричина: 123123123	\N	[]	\N	\N	\N	\N	\N	\N	\N	\N	2025-10-16 08:36:14.090028+00	2025-10-16 08:57:49.549833+00	\N	1	f	\N	[]	\N	\N	f	\N	\N	\N
251016-004	2	Электрика	Отменена	Квартира 1, Yangi Olmazor, 14V, (Фаза 1 (ЛОТ 4))	тестовая заявка	\N	Срочная	[]	\N	Отклонена менеджером Andrey Afanasyev 16.10.2025 08:58\nПричина: 2131231	\N	[]	\N	\N	\N	\N	\N	\N	\N	\N	2025-10-16 08:47:41.823913+00	2025-10-16 08:58:32.788249+00	\N	1	f	\N	[]	\N	\N	f	\N	\N	\N
251016-011	2	Электрика	Новая	Квартира 1, Yangi Olmazor, 14V, (Фаза 1 (ЛОТ 4))	тестовая заявка 1	\N	Критическая	["AgACAgIAAxkBAAIyomjxLApUTNMM1Q3VEl2OhQ4eA1X3AAJO_zEbxV2JS_8hIykQTo3uAQADAgADeQADNgQ"]	\N	\N	\N	[]	\N	\N	\N	\N	\N	\N	\N	\N	2025-10-16 17:31:58.196556+00	\N	\N	1	f	\N	[]	\N	\N	f	\N	\N	\N
251016-009	2	Безопасность	Принято	Дом: Yangi Olmazor, 14V	тестовая заявка 7	\N	Средняя	[]	2	\n[Исполнитель] Работа выполнена: 🛠 Активные заявки	\N	[]	individual	\N	2025-10-16 10:24:14.106135+00	2	\N	\N	\N	\N	2025-10-16 08:49:54.638351+00	2025-10-16 17:32:12.945321+00	2025-10-16 17:32:12.955144+00	\N	f	\N	[]	\N	\N	f	\N	\N	\N
251016-007	2	HVAC	В работе	Квартира 1, Yangi Olmazor, 14V, (Фаза 1 (ЛОТ 4))	тестовая заявка 7	\N	Обычная	[]	2	\n[Исполнитель] Работа выполнена: 	\N	[]	individual	hvac	2025-10-16 17:32:39.634555+00	2	\N	\N	\N	\N	2025-10-16 08:49:14.661371+00	2025-10-16 17:32:39.627478+00	\N	1	t	ответ на заявка возврат	[]	2025-10-16 17:32:28.165304+00	2	f	\N	\N	\N
251016-006	2	Сантехника	В работе	Квартира 1, Yangi Olmazor, 14V, (Фаза 1 (ЛОТ 4))	тестовая заявка 7	\N	Срочная	[]	26	\n[Исполнитель] Требуется закуп: 🛠 Активные заявки	\N	[]	individual	\N	2025-10-16 11:28:19.575163+00	2	\N	\N	123	Запрошенные материалы: Не указано\nКомментарий менеджера: 123\nОбновлено: 16.10.2025 11:29	2025-10-16 08:49:00.036997+00	2025-10-16 11:29:11.838735+00	\N	1	f	\N	[]	\N	\N	f	\N	\N	\N
251016-010	2	Электрика	Принято	Квартира 1, Yangi Olmazor, 14V, (Фаза 1 (ЛОТ 4))	ффывфывфывфвфыв	\N	Срочная	[]	\N	\n[Исполнитель] Работа выполнена: ыв	\N	[]	group	electrician	2025-10-16 10:24:34.896069+00	2	\N	\N	\N	\N	2025-10-16 10:04:45.203403+00	2025-10-16 11:53:15.41631+00	2025-10-16 11:53:15.429568+00	1	f	\N	[]	\N	\N	f	\N	\N	\N
251016-005	2	Электрика	В работе	Квартира 1, Yangi Olmazor, 14V, (Фаза 1 (ЛОТ 4))	❌ Ошибка при создании заявки. Попробуйте ещё раз.	\N	Критическая	[]	2	\N	\N	[]	individual	\N	2025-10-16 11:15:58.067965+00	2	\N	\N	\N	\N	2025-10-16 08:48:26.818467+00	2025-10-16 11:15:58.051715+00	\N	1	f	\N	[]	\N	\N	f	\N	\N	\N
\.


--
-- Data for Name: shift_assignments; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.shift_assignments (id, shift_id, request_number, assignment_priority, estimated_duration, assignment_order, ai_score, confidence_level, specialization_match_score, geographic_score, workload_score, status, auto_assigned, confirmed_by_executor, assigned_at, started_at, completed_at, planned_start_at, planned_completion_at, assignment_reason, notes, executor_instructions, actual_duration, execution_quality_rating, had_issues, issues_description, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: shift_schedules; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.shift_schedules (id, date, planned_coverage, actual_coverage, planned_specialization_coverage, actual_specialization_coverage, predicted_requests, actual_requests, prediction_accuracy, recommended_shifts, actual_shifts, optimization_score, coverage_percentage, load_balance_score, special_conditions, manual_adjustments, notes, status, created_by, auto_generated, version, created_at, updated_at) FROM stdin;
12	2025-09-19	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:38:08.172013+00	2025-09-20 22:03:31.532462+00
13	2025-09-20	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:38:08.172013+00	2025-09-20 22:03:31.532462+00
14	2025-09-21	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:38:08.172013+00	2025-09-20 22:03:31.532462+00
4	2025-09-11	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	50	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-09 18:25:01.168268+00	2025-09-10 18:42:08.304427+00
22	2025-09-29	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.762766+00	2025-09-22 08:00:00.28097+00
23	2025-09-30	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.762766+00	2025-09-22 08:00:00.28097+00
24	2025-10-01	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.762766+00	2025-09-22 08:00:00.28097+00
1	2025-09-08	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	50	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-09 18:25:01.168268+00	2025-09-10 18:42:43.934904+00
2	2025-09-09	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	50	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-09 18:25:01.168268+00	2025-09-10 18:42:43.934904+00
3	2025-09-10	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	50	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-09 18:25:01.168268+00	2025-09-10 18:42:43.934904+00
5	2025-09-12	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	50	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-09 18:25:01.168268+00	2025-09-10 18:42:43.934904+00
6	2025-09-13	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	55	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-09 18:25:01.168268+00	2025-09-10 18:42:43.934904+00
7	2025-09-14	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	55	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-09 18:25:01.168268+00	2025-09-10 18:42:43.934904+00
31	2025-10-22	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:00:00.236115+00	2025-10-16 12:08:38.564353+00
32	2025-10-23	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:00:00.236115+00	2025-10-16 12:08:38.564353+00
33	2025-10-24	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:00:00.236115+00	2025-10-16 12:08:38.564353+00
34	2025-10-25	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:00:00.236115+00	2025-10-16 12:08:38.564353+00
35	2025-10-26	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:00:00.236115+00	2025-10-16 12:08:38.564353+00
15	2025-09-22	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	50	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.732637+00	2025-09-11 07:33:13.830633+00
16	2025-09-23	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	50	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.732637+00	2025-09-11 07:33:13.830633+00
17	2025-09-24	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	50	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.732637+00	2025-09-11 07:33:13.830633+00
18	2025-09-25	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	50	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.732637+00	2025-09-11 07:33:13.830633+00
19	2025-09-26	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	50	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.732637+00	2025-09-11 07:33:13.830633+00
20	2025-09-27	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	55	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.732637+00	2025-09-11 07:33:13.830633+00
21	2025-09-28	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	55	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.732637+00	2025-09-11 07:33:13.830633+00
8	2025-09-15	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:38:08.172013+00	2025-09-20 22:03:31.532462+00
9	2025-09-16	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:38:08.172013+00	2025-09-20 22:03:31.532462+00
10	2025-09-17	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:38:08.172013+00	2025-09-20 22:03:31.532462+00
11	2025-09-18	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:38:08.172013+00	2025-09-20 22:03:31.532462+00
25	2025-10-02	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.762766+00	2025-09-22 08:00:00.28097+00
26	2025-10-03	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.762766+00	2025-09-22 08:00:00.28097+00
27	2025-10-04	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.762766+00	2025-09-22 08:00:00.28097+00
28	2025-10-05	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-09-10 18:43:03.762766+00	2025-09-22 08:00:00.28097+00
43	2025-10-27	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	57.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:38.838657+00	2025-10-20 08:00:00.363096+00
44	2025-10-28	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	57.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:38.838657+00	2025-10-20 08:00:00.363096+00
45	2025-10-29	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	57.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:38.838657+00	2025-10-20 08:00:00.363096+00
36	2025-10-13	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	57.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:53:28.447098+00	2025-10-16 18:49:59.607473+00
37	2025-10-14	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	52.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:53:28.447098+00	2025-10-16 18:49:59.607473+00
38	2025-10-15	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	52.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:53:28.447098+00	2025-10-16 18:49:59.607473+00
29	2025-10-20	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:00:00.236115+00	2025-10-16 12:08:38.564353+00
30	2025-10-21	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:00:00.236115+00	2025-10-16 12:08:38.564353+00
50	2025-11-03	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:39.126849+00	2025-10-16 12:10:20.737389+00
51	2025-11-04	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:39.126849+00	2025-10-16 12:10:20.737389+00
52	2025-11-05	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:39.126849+00	2025-10-16 12:10:20.737389+00
53	2025-11-06	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:39.126849+00	2025-10-16 12:10:20.737389+00
54	2025-11-07	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:39.126849+00	2025-10-16 12:10:20.737389+00
55	2025-11-08	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:39.126849+00	2025-10-16 12:10:20.737389+00
56	2025-11-09	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	70	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:39.126849+00	2025-10-16 12:10:20.737389+00
39	2025-10-16	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	52.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:53:28.447098+00	2025-10-16 18:49:59.607473+00
40	2025-10-17	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	57.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:53:28.447098+00	2025-10-16 18:49:59.607473+00
41	2025-10-18	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	57.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:53:28.447098+00	2025-10-16 18:49:59.607473+00
46	2025-10-30	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	57.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:38.838657+00	2025-10-20 08:00:00.363096+00
47	2025-10-31	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	57.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:38.838657+00	2025-10-20 08:00:00.363096+00
48	2025-11-01	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	57.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:38.838657+00	2025-10-20 08:00:00.363096+00
49	2025-11-02	\N	{"shifts_created": 5}	\N	\N	\N	0	\N	\N	0	57.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-16 12:08:38.838657+00	2025-10-20 08:00:00.363096+00
42	2025-10-19	\N	{"shifts_created": 0}	\N	\N	\N	0	\N	\N	0	57.5	\N	\N	\N	\N	\N	draft	\N	f	1	2025-10-13 08:53:28.447098+00	2025-10-16 18:49:59.607473+00
\.


--
-- Data for Name: shift_templates; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.shift_templates (id, name, description, start_hour, start_minute, duration_hours, required_specializations, min_executors, max_executors, default_max_requests, coverage_areas, geographic_zone, priority_level, auto_create, days_of_week, advance_days, is_active, default_shift_type, settings, created_at, updated_at) FROM stdin;
4	Дежурный электрик	Смена дежурного электрика	9	0	24	["electric"]	1	3	10	\N	\N	1	t	[1, 2, 3, 4, 5, 6, 7]	1	t	regular	\N	2025-09-12 07:25:31.388695+00	2025-09-12 07:46:36.087825+00
5	Смена уборки	Шаблон рабочая смена	9	0	8	["cleaning"]	1	3	10	\N	\N	1	t	[1, 2, 3, 4, 5, 6, 7]	1	t	regular	\N	2025-09-12 07:25:54.534046+00	2025-09-12 07:46:36.087825+00
6	Дежурный сантехник	Смена дежурного сантехника	9	0	24	["plumbing"]	1	3	10	\N	\N	1	t	[1, 2, 3, 4, 5, 6, 7]	1	t	regular	\N	2025-09-12 07:38:14.32402+00	2025-09-12 07:46:36.087825+00
7	Дежурный охранник	Шаблон Дежурный охранник	9	0	24	["security"]	1	3	10	\N	\N	1	t	[1, 2, 3, 4, 5, 6, 7]	1	t	regular	\N	2025-09-12 07:41:42.944889+00	2025-09-12 07:46:36.087825+00
9	Садовник	Шаблон Садовник	9	0	12	["universal"]	1	3	10	\N	\N	1	t	[1, 2, 3, 4, 5, 6, 7]	1	t	regular	\N	2025-09-12 07:43:33.187297+00	2025-09-12 07:46:36.087825+00
\.


--
-- Data for Name: shift_transfers; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.shift_transfers (id, shift_id, from_executor_id, to_executor_id, status, reason, comment, urgency_level, created_at, assigned_at, responded_at, completed_at, auto_assigned, retry_count, max_retries) FROM stdin;
\.


--
-- Data for Name: shifts; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.shifts (id, user_id, start_time, end_time, status, notes, created_at, updated_at, shift_type, max_requests, current_request_count, priority_level, efficiency_score, planned_start_time, planned_end_time, specialization_focus, coverage_areas, completed_requests, average_response_time, quality_rating, shift_template_id, geographic_zone, average_completion_time) FROM stdin;
285	\N	2025-10-13 09:00:00+00	2025-10-14 09:00:00+00	planned	\N	2025-10-16 18:49:57.631611+00	\N	regular	10	0	1	\N	2025-10-13 09:00:00+00	2025-10-14 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
286	\N	2025-10-13 09:00:00+00	2025-10-13 17:00:00+00	planned	\N	2025-10-16 18:49:57.657942+00	\N	regular	10	0	1	\N	2025-10-13 09:00:00+00	2025-10-13 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
287	\N	2025-10-13 09:00:00+00	2025-10-14 09:00:00+00	planned	\N	2025-10-16 18:49:57.663572+00	\N	regular	10	0	1	\N	2025-10-13 09:00:00+00	2025-10-14 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
288	\N	2025-10-13 09:00:00+00	2025-10-14 09:00:00+00	planned	\N	2025-10-16 18:49:57.67067+00	\N	regular	10	0	1	\N	2025-10-13 09:00:00+00	2025-10-14 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
289	\N	2025-10-13 09:00:00+00	2025-10-13 21:00:00+00	planned	\N	2025-10-16 18:49:57.675808+00	\N	regular	10	0	1	\N	2025-10-13 09:00:00+00	2025-10-13 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
290	\N	2025-10-14 09:00:00+00	2025-10-15 09:00:00+00	planned	\N	2025-10-16 18:49:57.680416+00	\N	regular	10	0	1	\N	2025-10-14 09:00:00+00	2025-10-15 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
291	\N	2025-10-14 09:00:00+00	2025-10-14 17:00:00+00	planned	\N	2025-10-16 18:49:57.684055+00	\N	regular	10	0	1	\N	2025-10-14 09:00:00+00	2025-10-14 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
292	\N	2025-10-14 09:00:00+00	2025-10-15 09:00:00+00	planned	\N	2025-10-16 18:49:57.687944+00	\N	regular	10	0	1	\N	2025-10-14 09:00:00+00	2025-10-15 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
293	\N	2025-10-14 09:00:00+00	2025-10-14 21:00:00+00	planned	\N	2025-10-16 18:49:57.692484+00	\N	regular	10	0	1	\N	2025-10-14 09:00:00+00	2025-10-14 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
294	\N	2025-10-15 09:00:00+00	2025-10-16 09:00:00+00	planned	\N	2025-10-16 18:49:57.696297+00	\N	regular	10	0	1	\N	2025-10-15 09:00:00+00	2025-10-16 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
295	\N	2025-10-15 09:00:00+00	2025-10-15 17:00:00+00	planned	\N	2025-10-16 18:49:57.699836+00	\N	regular	10	0	1	\N	2025-10-15 09:00:00+00	2025-10-15 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
296	\N	2025-10-15 09:00:00+00	2025-10-16 09:00:00+00	planned	\N	2025-10-16 18:49:57.703304+00	\N	regular	10	0	1	\N	2025-10-15 09:00:00+00	2025-10-16 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
297	\N	2025-10-15 09:00:00+00	2025-10-15 21:00:00+00	planned	\N	2025-10-16 18:49:57.707824+00	\N	regular	10	0	1	\N	2025-10-15 09:00:00+00	2025-10-15 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
298	\N	2025-10-16 09:00:00+00	2025-10-16 17:00:00+00	planned	\N	2025-10-16 18:49:57.71153+00	\N	regular	10	0	1	\N	2025-10-16 09:00:00+00	2025-10-16 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
299	\N	2025-10-16 09:00:00+00	2025-10-17 09:00:00+00	planned	\N	2025-10-16 18:49:57.715755+00	\N	regular	10	0	1	\N	2025-10-16 09:00:00+00	2025-10-17 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
300	\N	2025-10-16 09:00:00+00	2025-10-17 09:00:00+00	planned	\N	2025-10-16 18:49:57.719101+00	\N	regular	10	0	1	\N	2025-10-16 09:00:00+00	2025-10-17 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
301	\N	2025-10-16 09:00:00+00	2025-10-16 21:00:00+00	planned	\N	2025-10-16 18:49:57.72227+00	\N	regular	10	0	1	\N	2025-10-16 09:00:00+00	2025-10-16 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
302	\N	2025-10-17 09:00:00+00	2025-10-18 09:00:00+00	planned	\N	2025-10-16 18:49:57.725594+00	\N	regular	10	0	1	\N	2025-10-17 09:00:00+00	2025-10-18 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
303	\N	2025-10-17 09:00:00+00	2025-10-17 17:00:00+00	planned	\N	2025-10-16 18:49:57.728607+00	\N	regular	10	0	1	\N	2025-10-17 09:00:00+00	2025-10-17 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
304	\N	2025-10-17 09:00:00+00	2025-10-18 09:00:00+00	planned	\N	2025-10-16 18:49:57.731769+00	\N	regular	10	0	1	\N	2025-10-17 09:00:00+00	2025-10-18 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
305	\N	2025-10-17 09:00:00+00	2025-10-18 09:00:00+00	planned	\N	2025-10-16 18:49:57.734908+00	\N	regular	10	0	1	\N	2025-10-17 09:00:00+00	2025-10-18 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
306	\N	2025-10-17 09:00:00+00	2025-10-17 21:00:00+00	planned	\N	2025-10-16 18:49:57.738157+00	\N	regular	10	0	1	\N	2025-10-17 09:00:00+00	2025-10-17 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
307	\N	2025-10-18 09:00:00+00	2025-10-19 09:00:00+00	planned	\N	2025-10-16 18:49:57.741555+00	\N	regular	10	0	1	\N	2025-10-18 09:00:00+00	2025-10-19 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
308	\N	2025-10-18 09:00:00+00	2025-10-18 17:00:00+00	planned	\N	2025-10-16 18:49:57.744669+00	\N	regular	10	0	1	\N	2025-10-18 09:00:00+00	2025-10-18 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
309	\N	2025-10-18 09:00:00+00	2025-10-19 09:00:00+00	planned	\N	2025-10-16 18:49:57.747749+00	\N	regular	10	0	1	\N	2025-10-18 09:00:00+00	2025-10-19 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
310	\N	2025-10-18 09:00:00+00	2025-10-19 09:00:00+00	planned	\N	2025-10-16 18:49:57.750698+00	\N	regular	10	0	1	\N	2025-10-18 09:00:00+00	2025-10-19 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
311	\N	2025-10-18 09:00:00+00	2025-10-18 21:00:00+00	planned	\N	2025-10-16 18:49:57.753649+00	\N	regular	10	0	1	\N	2025-10-18 09:00:00+00	2025-10-18 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
312	\N	2025-10-19 09:00:00+00	2025-10-20 09:00:00+00	planned	\N	2025-10-16 18:49:57.756582+00	\N	regular	10	0	1	\N	2025-10-19 09:00:00+00	2025-10-20 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
313	\N	2025-10-19 09:00:00+00	2025-10-19 17:00:00+00	planned	\N	2025-10-16 18:49:57.759595+00	\N	regular	10	0	1	\N	2025-10-19 09:00:00+00	2025-10-19 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
314	\N	2025-10-19 09:00:00+00	2025-10-20 09:00:00+00	planned	\N	2025-10-16 18:49:57.763241+00	\N	regular	10	0	1	\N	2025-10-19 09:00:00+00	2025-10-20 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
315	\N	2025-10-19 09:00:00+00	2025-10-20 09:00:00+00	planned	\N	2025-10-16 18:49:57.766831+00	\N	regular	10	0	1	\N	2025-10-19 09:00:00+00	2025-10-20 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
316	\N	2025-10-19 09:00:00+00	2025-10-19 21:00:00+00	planned	\N	2025-10-16 18:49:57.771082+00	\N	regular	10	0	1	\N	2025-10-19 09:00:00+00	2025-10-19 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
317	\N	2025-10-20 09:00:00+00	2025-10-21 09:00:00+00	planned	\N	2025-10-19 00:30:00.050211+00	\N	regular	10	0	1	\N	2025-10-20 09:00:00+00	2025-10-21 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
318	\N	2025-10-20 09:00:00+00	2025-10-20 17:00:00+00	planned	\N	2025-10-19 00:30:00.115499+00	\N	regular	10	0	1	\N	2025-10-20 09:00:00+00	2025-10-20 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
319	\N	2025-10-20 09:00:00+00	2025-10-21 09:00:00+00	planned	\N	2025-10-19 00:30:00.121072+00	\N	regular	10	0	1	\N	2025-10-20 09:00:00+00	2025-10-21 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
320	\N	2025-10-20 09:00:00+00	2025-10-21 09:00:00+00	planned	\N	2025-10-19 00:30:00.125163+00	\N	regular	10	0	1	\N	2025-10-20 09:00:00+00	2025-10-21 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
321	\N	2025-10-20 09:00:00+00	2025-10-20 21:00:00+00	planned	\N	2025-10-19 00:30:00.128641+00	\N	regular	10	0	1	\N	2025-10-20 09:00:00+00	2025-10-20 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
322	\N	2025-10-21 09:00:00+00	2025-10-22 09:00:00+00	planned	\N	2025-10-20 00:30:00.03296+00	\N	regular	10	0	1	\N	2025-10-21 09:00:00+00	2025-10-22 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
323	\N	2025-10-21 09:00:00+00	2025-10-21 17:00:00+00	planned	\N	2025-10-20 00:30:00.104678+00	\N	regular	10	0	1	\N	2025-10-21 09:00:00+00	2025-10-21 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
324	\N	2025-10-21 09:00:00+00	2025-10-22 09:00:00+00	planned	\N	2025-10-20 00:30:00.109931+00	\N	regular	10	0	1	\N	2025-10-21 09:00:00+00	2025-10-22 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
325	\N	2025-10-21 09:00:00+00	2025-10-22 09:00:00+00	planned	\N	2025-10-20 00:30:00.113195+00	\N	regular	10	0	1	\N	2025-10-21 09:00:00+00	2025-10-22 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
326	\N	2025-10-21 09:00:00+00	2025-10-21 21:00:00+00	planned	\N	2025-10-20 00:30:00.116719+00	\N	regular	10	0	1	\N	2025-10-21 09:00:00+00	2025-10-21 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
327	\N	2025-10-27 09:00:00+00	2025-10-28 09:00:00+00	planned	\N	2025-10-20 08:00:00.107866+00	\N	regular	10	0	1	\N	2025-10-27 09:00:00+00	2025-10-28 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
328	\N	2025-10-27 09:00:00+00	2025-10-27 17:00:00+00	planned	\N	2025-10-20 08:00:00.199621+00	\N	regular	10	0	1	\N	2025-10-27 09:00:00+00	2025-10-27 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
329	\N	2025-10-27 09:00:00+00	2025-10-28 09:00:00+00	planned	\N	2025-10-20 08:00:00.204781+00	\N	regular	10	0	1	\N	2025-10-27 09:00:00+00	2025-10-28 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
330	\N	2025-10-27 09:00:00+00	2025-10-28 09:00:00+00	planned	\N	2025-10-20 08:00:00.209205+00	\N	regular	10	0	1	\N	2025-10-27 09:00:00+00	2025-10-28 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
331	\N	2025-10-27 09:00:00+00	2025-10-27 21:00:00+00	planned	\N	2025-10-20 08:00:00.213619+00	\N	regular	10	0	1	\N	2025-10-27 09:00:00+00	2025-10-27 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
332	\N	2025-10-28 09:00:00+00	2025-10-29 09:00:00+00	planned	\N	2025-10-20 08:00:00.21869+00	\N	regular	10	0	1	\N	2025-10-28 09:00:00+00	2025-10-29 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
333	\N	2025-10-28 09:00:00+00	2025-10-28 17:00:00+00	planned	\N	2025-10-20 08:00:00.222638+00	\N	regular	10	0	1	\N	2025-10-28 09:00:00+00	2025-10-28 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
334	\N	2025-10-28 09:00:00+00	2025-10-29 09:00:00+00	planned	\N	2025-10-20 08:00:00.227059+00	\N	regular	10	0	1	\N	2025-10-28 09:00:00+00	2025-10-29 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
335	\N	2025-10-28 09:00:00+00	2025-10-29 09:00:00+00	planned	\N	2025-10-20 08:00:00.230938+00	\N	regular	10	0	1	\N	2025-10-28 09:00:00+00	2025-10-29 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
336	\N	2025-10-28 09:00:00+00	2025-10-28 21:00:00+00	planned	\N	2025-10-20 08:00:00.23537+00	\N	regular	10	0	1	\N	2025-10-28 09:00:00+00	2025-10-28 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
337	\N	2025-10-29 09:00:00+00	2025-10-30 09:00:00+00	planned	\N	2025-10-20 08:00:00.239372+00	\N	regular	10	0	1	\N	2025-10-29 09:00:00+00	2025-10-30 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
338	\N	2025-10-29 09:00:00+00	2025-10-29 17:00:00+00	planned	\N	2025-10-20 08:00:00.24459+00	\N	regular	10	0	1	\N	2025-10-29 09:00:00+00	2025-10-29 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
339	\N	2025-10-29 09:00:00+00	2025-10-30 09:00:00+00	planned	\N	2025-10-20 08:00:00.248406+00	\N	regular	10	0	1	\N	2025-10-29 09:00:00+00	2025-10-30 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
340	\N	2025-10-29 09:00:00+00	2025-10-30 09:00:00+00	planned	\N	2025-10-20 08:00:00.252403+00	\N	regular	10	0	1	\N	2025-10-29 09:00:00+00	2025-10-30 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
341	\N	2025-10-29 09:00:00+00	2025-10-29 21:00:00+00	planned	\N	2025-10-20 08:00:00.2625+00	\N	regular	10	0	1	\N	2025-10-29 09:00:00+00	2025-10-29 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
342	\N	2025-10-30 09:00:00+00	2025-10-31 09:00:00+00	planned	\N	2025-10-20 08:00:00.268457+00	\N	regular	10	0	1	\N	2025-10-30 09:00:00+00	2025-10-31 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
343	\N	2025-10-30 09:00:00+00	2025-10-30 17:00:00+00	planned	\N	2025-10-20 08:00:00.27445+00	\N	regular	10	0	1	\N	2025-10-30 09:00:00+00	2025-10-30 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
344	\N	2025-10-30 09:00:00+00	2025-10-31 09:00:00+00	planned	\N	2025-10-20 08:00:00.279785+00	\N	regular	10	0	1	\N	2025-10-30 09:00:00+00	2025-10-31 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
345	\N	2025-10-30 09:00:00+00	2025-10-31 09:00:00+00	planned	\N	2025-10-20 08:00:00.284283+00	\N	regular	10	0	1	\N	2025-10-30 09:00:00+00	2025-10-31 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
346	\N	2025-10-30 09:00:00+00	2025-10-30 21:00:00+00	planned	\N	2025-10-20 08:00:00.291493+00	\N	regular	10	0	1	\N	2025-10-30 09:00:00+00	2025-10-30 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
347	\N	2025-10-31 09:00:00+00	2025-11-01 09:00:00+00	planned	\N	2025-10-20 08:00:00.296346+00	\N	regular	10	0	1	\N	2025-10-31 09:00:00+00	2025-11-01 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
348	\N	2025-10-31 09:00:00+00	2025-10-31 17:00:00+00	planned	\N	2025-10-20 08:00:00.302787+00	\N	regular	10	0	1	\N	2025-10-31 09:00:00+00	2025-10-31 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
349	\N	2025-10-31 09:00:00+00	2025-11-01 09:00:00+00	planned	\N	2025-10-20 08:00:00.30758+00	\N	regular	10	0	1	\N	2025-10-31 09:00:00+00	2025-11-01 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
350	\N	2025-10-31 09:00:00+00	2025-11-01 09:00:00+00	planned	\N	2025-10-20 08:00:00.311307+00	\N	regular	10	0	1	\N	2025-10-31 09:00:00+00	2025-11-01 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
351	\N	2025-10-31 09:00:00+00	2025-10-31 21:00:00+00	planned	\N	2025-10-20 08:00:00.314801+00	\N	regular	10	0	1	\N	2025-10-31 09:00:00+00	2025-10-31 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
352	\N	2025-11-01 09:00:00+00	2025-11-02 09:00:00+00	planned	\N	2025-10-20 08:00:00.319762+00	\N	regular	10	0	1	\N	2025-11-01 09:00:00+00	2025-11-02 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
353	\N	2025-11-01 09:00:00+00	2025-11-01 17:00:00+00	planned	\N	2025-10-20 08:00:00.323883+00	\N	regular	10	0	1	\N	2025-11-01 09:00:00+00	2025-11-01 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
354	\N	2025-11-01 09:00:00+00	2025-11-02 09:00:00+00	planned	\N	2025-10-20 08:00:00.328383+00	\N	regular	10	0	1	\N	2025-11-01 09:00:00+00	2025-11-02 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
355	\N	2025-11-01 09:00:00+00	2025-11-02 09:00:00+00	planned	\N	2025-10-20 08:00:00.332332+00	\N	regular	10	0	1	\N	2025-11-01 09:00:00+00	2025-11-02 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
356	\N	2025-11-01 09:00:00+00	2025-11-01 21:00:00+00	planned	\N	2025-10-20 08:00:00.336137+00	\N	regular	10	0	1	\N	2025-11-01 09:00:00+00	2025-11-01 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
357	\N	2025-11-02 09:00:00+00	2025-11-03 09:00:00+00	planned	\N	2025-10-20 08:00:00.340157+00	\N	regular	10	0	1	\N	2025-11-02 09:00:00+00	2025-11-03 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
358	\N	2025-11-02 09:00:00+00	2025-11-02 17:00:00+00	planned	\N	2025-10-20 08:00:00.344514+00	\N	regular	10	0	1	\N	2025-11-02 09:00:00+00	2025-11-02 17:00:00+00	["cleaning"]	null	0	\N	\N	5	\N	\N
359	\N	2025-11-02 09:00:00+00	2025-11-03 09:00:00+00	planned	\N	2025-10-20 08:00:00.348869+00	\N	regular	10	0	1	\N	2025-11-02 09:00:00+00	2025-11-03 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
360	\N	2025-11-02 09:00:00+00	2025-11-03 09:00:00+00	planned	\N	2025-10-20 08:00:00.353751+00	\N	regular	10	0	1	\N	2025-11-02 09:00:00+00	2025-11-03 09:00:00+00	["security"]	null	0	\N	\N	7	\N	\N
361	\N	2025-11-02 09:00:00+00	2025-11-02 21:00:00+00	planned	\N	2025-10-20 08:00:00.35884+00	\N	regular	10	0	1	\N	2025-11-02 09:00:00+00	2025-11-02 21:00:00+00	["universal"]	null	0	\N	\N	9	\N	\N
150	2	2025-10-14 09:00:00+00	2025-10-16 17:37:09.331114+00	completed	\N	2025-10-13 00:30:00.096499+00	2025-10-16 17:37:09.327928+00	regular	10	0	1	\N	2025-10-14 09:00:00+00	2025-10-15 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
213	2	2025-10-13 17:48:05.491409+00	2025-10-16 17:37:17.121983+00	completed	\N	2025-10-13 18:48:05.491409+00	2025-10-16 17:37:17.119879+00	regular	10	0	1	\N	\N	\N	\N	\N	0	\N	\N	\N	\N	\N
193	2	2025-10-16 09:00:00+00	2025-10-16 17:37:13.486035+00	completed	\N	2025-10-13 08:53:28.396175+00	2025-10-16 17:37:13.483009+00	regular	10	0	1	\N	2025-10-16 09:00:00+00	2025-10-17 09:00:00+00	["electric"]	null	0	\N	\N	4	\N	\N
214	26	2025-10-14 11:14:50.001833+00	2025-10-16 17:37:55.841725+00	completed	\N	2025-10-14 11:14:49.997397+00	2025-10-16 17:37:55.839813+00	regular	10	0	1	\N	\N	\N	\N	\N	0	\N	\N	\N	\N	\N
190	2	2025-10-15 09:00:00+00	2025-10-16 17:36:52.380424+00	completed	\N	2025-10-13 08:53:28.384319+00	2025-10-16 17:36:52.37615+00	regular	10	0	1	\N	2025-10-15 09:00:00+00	2025-10-16 09:00:00+00	["plumbing"]	null	0	\N	\N	6	\N	\N
\.


--
-- Data for Name: user_apartments; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.user_apartments (id, user_id, apartment_id, status, requested_at, reviewed_at, reviewed_by, admin_comment, is_owner, is_primary, created_at, updated_at) FROM stdin;
5	2	1	approved	2025-10-12 17:54:32.339594+00	2025-10-12 19:01:53.272944+00	2	ы	f	t	2025-10-12 17:54:32.339594+00	2025-10-12 19:01:53.272944+00
\.


--
-- Data for Name: user_documents; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.user_documents (id, user_id, document_type, file_id, file_name, file_size, verification_status, verification_notes, verified_by, verified_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: user_verifications; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.user_verifications (id, user_id, status, requested_info, requested_at, requested_by, admin_notes, verified_by, verified_at, created_at, updated_at) FROM stdin;
2	13	REQUESTED	{"type": "multiple_documents", "request_text": "Пришлите договор аренды (просто любое фото)", "requested_at": "2025-09-16T19:54:09.555138", "document_types": ["rental"]}	2025-09-16 19:54:09.559254+00	2	\N	\N	\N	2025-09-16 19:54:09.54337+00	\N
\.


--
-- Data for Name: user_yards; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.user_yards (id, user_id, yard_id, granted_at, granted_by, comment, created_at, updated_at) FROM stdin;
3	14	1	2025-10-13 08:54:06.031648+00	2	Добавлено администратором Andrey	2025-10-13 08:54:06.031648+00	\N
4	14	2	2025-10-13 08:54:08.076844+00	2	Добавлено администратором Andrey	2025-10-13 08:54:08.076844+00	\N
5	14	3	2025-10-13 08:54:09.455767+00	2	Добавлено администратором Andrey	2025-10-13 08:54:09.455767+00	\N
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.users (id, telegram_id, username, first_name, last_name, role, roles, active_role, status, language, phone, specialization, created_at, updated_at, verification_status, verification_notes, verification_date, verified_by, passport_series, passport_number, birth_date) FROM stdin;
16	12345	testuser	Test	User	admin	\N	\N	pending	ru	\N	\N	2025-09-17 15:33:24.369103+00	\N	pending	\N	\N	\N	\N	\N	\N
2	48617336	A_S_Afanasyev	Andrey	Afanasyev	manager	["applicant", "executor", "manager"]	manager	approved	ru	+998933900430	["electrician", "repair", "installation", "maintenance", "landscaping", "security", "hvac", "plumber", "cleaning"]	2025-08-24 14:19:24.168838+00	2025-10-16 18:14:43.757992+00	pending	\N	\N	\N	\N	\N	\N
26	6055402868	\N	Ivan	Ivan	executor	["executor"]	\N	approved	ru	+998777777777	["plumber", "electrician"]	2025-10-14 09:23:37.985941+00	2025-10-14 11:14:29.96402+00	pending	\N	\N	\N	\N	\N	\N
14	871196710	MEGraf77	Mikhail	MEG	applicant	\N	applicant	approved	ru	+79251937237	\N	2025-09-16 19:48:20.985733+00	2025-09-16 19:52:48.219515+00	pending	\N	\N	\N	\N	\N	\N
13	61022844	Nazya_Shlyk	Nazya	\N	applicant	["manager"]	manager	approved	ru	+998974796022	\N	2025-09-16 19:36:20.670338+00	2025-09-16 20:00:55.54743+00	requested	\N	\N	\N	\N	\N	\N
15	123456789	testuser	Test	User	applicant	\N	\N	approved	ru	\N	\N	2025-09-17 08:04:48.154344+00	\N	pending	\N	\N	\N	\N	\N	\N
\.


--
-- Data for Name: yards; Type: TABLE DATA; Schema: public; Owner: uk_bot
--

COPY public.yards (id, name, description, gps_latitude, gps_longitude, is_active, created_at, created_by, updated_at) FROM stdin;
1	Фаза 1 (ЛОТ 4)	\N	41.349778	69.246924	t	2025-10-12 15:09:44.137796+00	2	\N
2	Фаза 2	\N	41.349925	69.244803	t	2025-10-12 15:19:15.769313+00	2	\N
3	Фаза 3	\N	41.349794	69.248766	t	2025-10-12 15:24:09.905098+00	2	\N
\.


--
-- Name: access_rights_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.access_rights_id_seq', 1, false);


--
-- Name: apartments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.apartments_id_seq', 161, false);


--
-- Name: audit_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.audit_logs_id_seq', 881, true);


--
-- Name: buildings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.buildings_id_seq', 4, false);


--
-- Name: notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.notifications_id_seq', 1, false);


--
-- Name: planning_conflicts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.planning_conflicts_id_seq', 1, false);


--
-- Name: quarterly_plans_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.quarterly_plans_id_seq', 1, false);


--
-- Name: quarterly_shift_schedules_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.quarterly_shift_schedules_id_seq', 1, false);


--
-- Name: ratings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.ratings_id_seq', 8, true);


--
-- Name: request_assignments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.request_assignments_id_seq', 21, true);


--
-- Name: request_comments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.request_comments_id_seq', 8, true);


--
-- Name: shift_assignments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.shift_assignments_id_seq', 1, false);


--
-- Name: shift_schedules_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.shift_schedules_id_seq', 56, true);


--
-- Name: shift_templates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.shift_templates_id_seq', 9, true);


--
-- Name: shift_transfers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.shift_transfers_id_seq', 1, false);


--
-- Name: shifts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.shifts_id_seq', 361, true);


--
-- Name: user_apartments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.user_apartments_id_seq', 6, true);


--
-- Name: user_documents_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.user_documents_id_seq', 10, true);


--
-- Name: user_verifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.user_verifications_id_seq', 2, true);


--
-- Name: user_yards_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.user_yards_id_seq', 5, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.users_id_seq', 26, true);


--
-- Name: yards_id_seq; Type: SEQUENCE SET; Schema: public; Owner: uk_bot
--

SELECT pg_catalog.setval('public.yards_id_seq', 4, false);


--
-- Name: access_rights access_rights_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.access_rights
    ADD CONSTRAINT access_rights_pkey PRIMARY KEY (id);


--
-- Name: apartments apartments_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.apartments
    ADD CONSTRAINT apartments_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: buildings buildings_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.buildings
    ADD CONSTRAINT buildings_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: planning_conflicts planning_conflicts_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.planning_conflicts
    ADD CONSTRAINT planning_conflicts_pkey PRIMARY KEY (id);


--
-- Name: quarterly_plans quarterly_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.quarterly_plans
    ADD CONSTRAINT quarterly_plans_pkey PRIMARY KEY (id);


--
-- Name: quarterly_shift_schedules quarterly_shift_schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.quarterly_shift_schedules
    ADD CONSTRAINT quarterly_shift_schedules_pkey PRIMARY KEY (id);


--
-- Name: ratings ratings_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT ratings_pkey PRIMARY KEY (id);


--
-- Name: request_assignments request_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.request_assignments
    ADD CONSTRAINT request_assignments_pkey PRIMARY KEY (id);


--
-- Name: request_comments request_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.request_comments
    ADD CONSTRAINT request_comments_pkey PRIMARY KEY (id);


--
-- Name: requests requests_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.requests
    ADD CONSTRAINT requests_pkey PRIMARY KEY (request_number);


--
-- Name: shift_assignments shift_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_assignments
    ADD CONSTRAINT shift_assignments_pkey PRIMARY KEY (id);


--
-- Name: shift_schedules shift_schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_schedules
    ADD CONSTRAINT shift_schedules_pkey PRIMARY KEY (id);


--
-- Name: shift_templates shift_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_templates
    ADD CONSTRAINT shift_templates_pkey PRIMARY KEY (id);


--
-- Name: shift_transfers shift_transfers_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_transfers
    ADD CONSTRAINT shift_transfers_pkey PRIMARY KEY (id);


--
-- Name: shifts shifts_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shifts
    ADD CONSTRAINT shifts_pkey PRIMARY KEY (id);


--
-- Name: apartments uix_building_apartment; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.apartments
    ADD CONSTRAINT uix_building_apartment UNIQUE (building_id, apartment_number);


--
-- Name: user_apartments uix_user_apartment; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_apartments
    ADD CONSTRAINT uix_user_apartment UNIQUE (user_id, apartment_id);


--
-- Name: user_yards uix_user_yard; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_yards
    ADD CONSTRAINT uix_user_yard UNIQUE (user_id, yard_id);


--
-- Name: user_apartments user_apartments_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_apartments
    ADD CONSTRAINT user_apartments_pkey PRIMARY KEY (id);


--
-- Name: user_documents user_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_documents
    ADD CONSTRAINT user_documents_pkey PRIMARY KEY (id);


--
-- Name: user_verifications user_verifications_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_verifications
    ADD CONSTRAINT user_verifications_pkey PRIMARY KEY (id);


--
-- Name: user_yards user_yards_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_yards
    ADD CONSTRAINT user_yards_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: yards yards_name_key; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.yards
    ADD CONSTRAINT yards_name_key UNIQUE (name);


--
-- Name: yards yards_pkey; Type: CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.yards
    ADD CONSTRAINT yards_pkey PRIMARY KEY (id);


--
-- Name: idx_access_rights_active; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_access_rights_active ON public.access_rights USING btree (is_active);


--
-- Name: idx_access_rights_level; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_access_rights_level ON public.access_rights USING btree (access_level);


--
-- Name: idx_access_rights_user_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_access_rights_user_id ON public.access_rights USING btree (user_id);


--
-- Name: idx_apartments_building_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_apartments_building_id ON public.apartments USING btree (building_id);


--
-- Name: idx_apartments_is_active; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_apartments_is_active ON public.apartments USING btree (is_active);


--
-- Name: idx_apartments_number; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_apartments_number ON public.apartments USING btree (apartment_number);


--
-- Name: idx_audit_logs_telegram_user_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_audit_logs_telegram_user_id ON public.audit_logs USING btree (telegram_user_id);


--
-- Name: idx_buildings_address; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_buildings_address ON public.buildings USING btree (address);


--
-- Name: idx_buildings_is_active; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_buildings_is_active ON public.buildings USING btree (is_active);


--
-- Name: idx_buildings_yard_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_buildings_yard_id ON public.buildings USING btree (yard_id);


--
-- Name: idx_requests_apartment_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_requests_apartment_id ON public.requests USING btree (apartment_id);


--
-- Name: idx_requests_is_returned; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_requests_is_returned ON public.requests USING btree (is_returned);


--
-- Name: idx_requests_manager_confirmed; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_requests_manager_confirmed ON public.requests USING btree (manager_confirmed);


--
-- Name: idx_user_apartments_apartment_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_user_apartments_apartment_id ON public.user_apartments USING btree (apartment_id);


--
-- Name: idx_user_apartments_status; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_user_apartments_status ON public.user_apartments USING btree (status);


--
-- Name: idx_user_apartments_user_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_user_apartments_user_id ON public.user_apartments USING btree (user_id);


--
-- Name: idx_user_documents_status; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_user_documents_status ON public.user_documents USING btree (verification_status);


--
-- Name: idx_user_documents_user_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_user_documents_user_id ON public.user_documents USING btree (user_id);


--
-- Name: idx_user_verifications_status; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_user_verifications_status ON public.user_verifications USING btree (status);


--
-- Name: idx_user_verifications_user_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_user_verifications_user_id ON public.user_verifications USING btree (user_id);


--
-- Name: idx_yards_is_active; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_yards_is_active ON public.yards USING btree (is_active);


--
-- Name: idx_yards_name; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX idx_yards_name ON public.yards USING btree (name);


--
-- Name: ix_audit_logs_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_audit_logs_id ON public.audit_logs USING btree (id);


--
-- Name: ix_notifications_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_notifications_id ON public.notifications USING btree (id);


--
-- Name: ix_planning_conflicts_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_planning_conflicts_id ON public.planning_conflicts USING btree (id);


--
-- Name: ix_quarterly_plans_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_quarterly_plans_id ON public.quarterly_plans USING btree (id);


--
-- Name: ix_quarterly_shift_schedules_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_quarterly_shift_schedules_id ON public.quarterly_shift_schedules USING btree (id);


--
-- Name: ix_ratings_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_ratings_id ON public.ratings USING btree (id);


--
-- Name: ix_request_assignments_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_request_assignments_id ON public.request_assignments USING btree (id);


--
-- Name: ix_request_comments_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_request_comments_id ON public.request_comments USING btree (id);


--
-- Name: ix_requests_request_number; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_requests_request_number ON public.requests USING btree (request_number);


--
-- Name: ix_shift_assignments_assigned_at; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_assignments_assigned_at ON public.shift_assignments USING btree (assigned_at);


--
-- Name: ix_shift_assignments_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_assignments_id ON public.shift_assignments USING btree (id);


--
-- Name: ix_shift_assignments_request_number; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_assignments_request_number ON public.shift_assignments USING btree (request_number);


--
-- Name: ix_shift_assignments_shift_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_assignments_shift_id ON public.shift_assignments USING btree (shift_id);


--
-- Name: ix_shift_schedules_date; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE UNIQUE INDEX ix_shift_schedules_date ON public.shift_schedules USING btree (date);


--
-- Name: ix_shift_schedules_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_schedules_id ON public.shift_schedules USING btree (id);


--
-- Name: ix_shift_templates_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_templates_id ON public.shift_templates USING btree (id);


--
-- Name: ix_shift_transfers_assigned_at; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_transfers_assigned_at ON public.shift_transfers USING btree (assigned_at);


--
-- Name: ix_shift_transfers_created_at; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_transfers_created_at ON public.shift_transfers USING btree (created_at);


--
-- Name: ix_shift_transfers_from_executor_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_transfers_from_executor_id ON public.shift_transfers USING btree (from_executor_id);


--
-- Name: ix_shift_transfers_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_transfers_id ON public.shift_transfers USING btree (id);


--
-- Name: ix_shift_transfers_reason; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_transfers_reason ON public.shift_transfers USING btree (reason);


--
-- Name: ix_shift_transfers_shift_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_transfers_shift_id ON public.shift_transfers USING btree (shift_id);


--
-- Name: ix_shift_transfers_status; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_transfers_status ON public.shift_transfers USING btree (status);


--
-- Name: ix_shift_transfers_to_executor_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shift_transfers_to_executor_id ON public.shift_transfers USING btree (to_executor_id);


--
-- Name: ix_shifts_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_shifts_id ON public.shifts USING btree (id);


--
-- Name: ix_user_yards_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_user_yards_id ON public.user_yards USING btree (id);


--
-- Name: ix_user_yards_user_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_user_yards_user_id ON public.user_yards USING btree (user_id);


--
-- Name: ix_user_yards_yard_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_user_yards_yard_id ON public.user_yards USING btree (yard_id);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_users_telegram_id; Type: INDEX; Schema: public; Owner: uk_bot
--

CREATE UNIQUE INDEX ix_users_telegram_id ON public.users USING btree (telegram_id);


--
-- Name: access_rights update_access_rights_updated_at; Type: TRIGGER; Schema: public; Owner: uk_bot
--

CREATE TRIGGER update_access_rights_updated_at BEFORE UPDATE ON public.access_rights FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: user_documents update_user_documents_updated_at; Type: TRIGGER; Schema: public; Owner: uk_bot
--

CREATE TRIGGER update_user_documents_updated_at BEFORE UPDATE ON public.user_documents FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: user_verifications update_user_verifications_updated_at; Type: TRIGGER; Schema: public; Owner: uk_bot
--

CREATE TRIGGER update_user_verifications_updated_at BEFORE UPDATE ON public.user_verifications FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: access_rights access_rights_granted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.access_rights
    ADD CONSTRAINT access_rights_granted_by_fkey FOREIGN KEY (granted_by) REFERENCES public.users(id);


--
-- Name: access_rights access_rights_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.access_rights
    ADD CONSTRAINT access_rights_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: apartments apartments_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.apartments
    ADD CONSTRAINT apartments_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id) ON DELETE CASCADE;


--
-- Name: apartments apartments_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.apartments
    ADD CONSTRAINT apartments_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: audit_logs audit_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: buildings buildings_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.buildings
    ADD CONSTRAINT buildings_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: buildings buildings_yard_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.buildings
    ADD CONSTRAINT buildings_yard_id_fkey FOREIGN KEY (yard_id) REFERENCES public.yards(id) ON DELETE CASCADE;


--
-- Name: requests fk_requests_manager_confirmed_by_users; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.requests
    ADD CONSTRAINT fk_requests_manager_confirmed_by_users FOREIGN KEY (manager_confirmed_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: requests fk_requests_returned_by_users; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.requests
    ADD CONSTRAINT fk_requests_returned_by_users FOREIGN KEY (returned_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: planning_conflicts planning_conflicts_quarterly_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.planning_conflicts
    ADD CONSTRAINT planning_conflicts_quarterly_plan_id_fkey FOREIGN KEY (quarterly_plan_id) REFERENCES public.quarterly_plans(id);


--
-- Name: planning_conflicts planning_conflicts_resolved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.planning_conflicts
    ADD CONSTRAINT planning_conflicts_resolved_by_fkey FOREIGN KEY (resolved_by) REFERENCES public.users(id);


--
-- Name: quarterly_plans quarterly_plans_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.quarterly_plans
    ADD CONSTRAINT quarterly_plans_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: quarterly_shift_schedules quarterly_shift_schedules_actual_shift_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.quarterly_shift_schedules
    ADD CONSTRAINT quarterly_shift_schedules_actual_shift_id_fkey FOREIGN KEY (actual_shift_id) REFERENCES public.shifts(id);


--
-- Name: quarterly_shift_schedules quarterly_shift_schedules_assigned_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.quarterly_shift_schedules
    ADD CONSTRAINT quarterly_shift_schedules_assigned_user_id_fkey FOREIGN KEY (assigned_user_id) REFERENCES public.users(id);


--
-- Name: quarterly_shift_schedules quarterly_shift_schedules_quarterly_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.quarterly_shift_schedules
    ADD CONSTRAINT quarterly_shift_schedules_quarterly_plan_id_fkey FOREIGN KEY (quarterly_plan_id) REFERENCES public.quarterly_plans(id);


--
-- Name: ratings ratings_request_number_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT ratings_request_number_fkey FOREIGN KEY (request_number) REFERENCES public.requests(request_number);


--
-- Name: ratings ratings_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT ratings_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: request_assignments request_assignments_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.request_assignments
    ADD CONSTRAINT request_assignments_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: request_assignments request_assignments_executor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.request_assignments
    ADD CONSTRAINT request_assignments_executor_id_fkey FOREIGN KEY (executor_id) REFERENCES public.users(id);


--
-- Name: request_assignments request_assignments_request_number_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.request_assignments
    ADD CONSTRAINT request_assignments_request_number_fkey FOREIGN KEY (request_number) REFERENCES public.requests(request_number);


--
-- Name: request_comments request_comments_request_number_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.request_comments
    ADD CONSTRAINT request_comments_request_number_fkey FOREIGN KEY (request_number) REFERENCES public.requests(request_number);


--
-- Name: request_comments request_comments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.request_comments
    ADD CONSTRAINT request_comments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: requests requests_apartment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.requests
    ADD CONSTRAINT requests_apartment_id_fkey FOREIGN KEY (apartment_id) REFERENCES public.apartments(id);


--
-- Name: requests requests_assigned_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.requests
    ADD CONSTRAINT requests_assigned_by_fkey FOREIGN KEY (assigned_by) REFERENCES public.users(id);


--
-- Name: requests requests_executor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.requests
    ADD CONSTRAINT requests_executor_id_fkey FOREIGN KEY (executor_id) REFERENCES public.users(id);


--
-- Name: requests requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.requests
    ADD CONSTRAINT requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: shift_assignments shift_assignments_request_number_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_assignments
    ADD CONSTRAINT shift_assignments_request_number_fkey FOREIGN KEY (request_number) REFERENCES public.requests(request_number) ON DELETE CASCADE;


--
-- Name: shift_assignments shift_assignments_shift_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_assignments
    ADD CONSTRAINT shift_assignments_shift_id_fkey FOREIGN KEY (shift_id) REFERENCES public.shifts(id) ON DELETE CASCADE;


--
-- Name: shift_schedules shift_schedules_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_schedules
    ADD CONSTRAINT shift_schedules_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: shift_transfers shift_transfers_from_executor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_transfers
    ADD CONSTRAINT shift_transfers_from_executor_id_fkey FOREIGN KEY (from_executor_id) REFERENCES public.users(id);


--
-- Name: shift_transfers shift_transfers_shift_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_transfers
    ADD CONSTRAINT shift_transfers_shift_id_fkey FOREIGN KEY (shift_id) REFERENCES public.shifts(id);


--
-- Name: shift_transfers shift_transfers_to_executor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shift_transfers
    ADD CONSTRAINT shift_transfers_to_executor_id_fkey FOREIGN KEY (to_executor_id) REFERENCES public.users(id);


--
-- Name: shifts shifts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.shifts
    ADD CONSTRAINT shifts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_apartments user_apartments_apartment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_apartments
    ADD CONSTRAINT user_apartments_apartment_id_fkey FOREIGN KEY (apartment_id) REFERENCES public.apartments(id) ON DELETE CASCADE;


--
-- Name: user_apartments user_apartments_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_apartments
    ADD CONSTRAINT user_apartments_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: user_apartments user_apartments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_apartments
    ADD CONSTRAINT user_apartments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_documents user_documents_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_documents
    ADD CONSTRAINT user_documents_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_documents user_documents_verified_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_documents
    ADD CONSTRAINT user_documents_verified_by_fkey FOREIGN KEY (verified_by) REFERENCES public.users(id);


--
-- Name: user_verifications user_verifications_requested_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_verifications
    ADD CONSTRAINT user_verifications_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: user_verifications user_verifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_verifications
    ADD CONSTRAINT user_verifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_verifications user_verifications_verified_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_verifications
    ADD CONSTRAINT user_verifications_verified_by_fkey FOREIGN KEY (verified_by) REFERENCES public.users(id);


--
-- Name: user_yards user_yards_granted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_yards
    ADD CONSTRAINT user_yards_granted_by_fkey FOREIGN KEY (granted_by) REFERENCES public.users(id);


--
-- Name: user_yards user_yards_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_yards
    ADD CONSTRAINT user_yards_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_yards user_yards_yard_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.user_yards
    ADD CONSTRAINT user_yards_yard_id_fkey FOREIGN KEY (yard_id) REFERENCES public.yards(id) ON DELETE CASCADE;


--
-- Name: yards yards_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: uk_bot
--

ALTER TABLE ONLY public.yards
    ADD CONSTRAINT yards_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict liAvbkkTZ5o4EKalVUbiR5C1eYSIs4Gjxt0l9RBNsAC9bHwjEbjrWEeXvunis5W

