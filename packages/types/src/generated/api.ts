/* eslint-disable */
/**
 * AUTO-GENERATED from schemas/openapi.json (apps/api) — do not edit by hand.
 * Regenerate with: make schemas
 */

export interface paths {
    "/api/clips/{clip_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Clip */
        get: operations["get_clip_api_clips__clip_id__get"];
        put?: never;
        post?: never;
        /** Delete Clip */
        delete: operations["delete_clip_api_clips__clip_id__delete"];
        options?: never;
        head?: never;
        /** Update Clip */
        patch: operations["update_clip_api_clips__clip_id__patch"];
        trace?: never;
    };
    "/api/clips/{clip_id}/proxy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Clip Proxy
         * @description The clip's preview copy (seekable; created by a `proxy` job).
         */
        get: operations["clip_proxy_api_clips__clip_id__proxy_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/clips/{clip_id}/waveform": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Clip Waveform
         * @description Peak levels of the clip's own audio (sample 0 = start of its audio).
         */
        get: operations["clip_waveform_api_clips__clip_id__waveform_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exports/{export_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Export */
        delete: operations["delete_export_api_exports__export_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/exports/{export_id}/file": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download Export
         * @description The rendered file (supports HTTP range requests, so a video player can seek).
         */
        get: operations["download_export_api_exports__export_id__file_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Job */
        get: operations["get_job_api_jobs__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/jobs/{job_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Cancel Job
         * @description Queued jobs are cancelled at once; running jobs stop at their next checkpoint.
         */
        post: operations["cancel_job_api_jobs__job_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/jobs/{job_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Job Events
         * @description Server-Sent Events: a ``job`` event whenever the job changes; ends when it finishes.
         */
        get: operations["job_events_api_jobs__job_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/jobs/{job_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Retry Job
         * @description Start a new job with the same kind and parameters as a failed/cancelled one.
         */
        post: operations["retry_job_api_jobs__job_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/plugin/v1/handshake": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Handshake
         * @description Engine + API version and what this engine can do. Plugins check
         *     ``api_version`` (same major) and ``capabilities`` before anything else.
         */
        get: operations["handshake_api_plugin_v1_handshake_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/plugin/v1/presets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Presets */
        get: operations["list_presets_api_plugin_v1_presets_get"];
        put?: never;
        /** Create Preset */
        post: operations["create_preset_api_plugin_v1_presets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/plugin/v1/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Session
         * @description Create a session (and project) from the clips selected in the host.
         *     Idempotent on ``(host.app, host_sequence_id)``: the same clips reuse the
         *     existing project, so its analysis cache makes a re-run fast.
         */
        post: operations["create_session_api_plugin_v1_sessions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/plugin/v1/sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Session */
        get: operations["get_session_api_plugin_v1_sessions__session_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/plugin/v1/sessions/{session_id}/editplan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Editplan
         * @description The edit as host operations (default: latest version, the session's method).
         */
        get: operations["get_editplan_api_plugin_v1_sessions__session_id__editplan_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/plugin/v1/sessions/{session_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Session Events
         * @description SSE: ``progress`` while the job runs, then ``plan_ready`` (with the plan
         *     summary) or ``error`` (``{code, message, hint}``); the stream then ends.
         */
        get: operations["session_events_api_plugin_v1_sessions__session_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/plugin/v1/sessions/{session_id}/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Session
         * @description Write the plan as a file the host can import (Rule C fallback).
         *
         *     ``fcpxml`` with method ``multicam`` (or ``fcpxml_multicam``) writes a multicam
         *     clip with angle switches (Final Cut, Resolve).
         */
        get: operations["export_session_api_plugin_v1_sessions__session_id__export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/plugin/v1/sessions/{session_id}/feedback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Feedback
         * @description Store the editor's final timeline next to the auto edit ("learn my style", PL8).
         */
        post: operations["feedback_api_plugin_v1_sessions__session_id__feedback_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/plugin/v1/sessions/{session_id}/run": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Run Session */
        post: operations["run_session_api_plugin_v1_sessions__session_id__run_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/plugin/v1/sessions/{session_id}/setup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Setup Session
         * @description Who is who (roles or a full layout), editing style, apply method.
         */
        patch: operations["setup_session_api_plugin_v1_sessions__session_id__setup_patch"];
        trace?: never;
    };
    "/api/plugin/v1/sessions/{session_id}/social": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Social Clips
         * @description Social clips (in/out -> one plan per aspect ratio) arrive in PL5.
         */
        post: operations["social_clips_api_plugin_v1_sessions__session_id__social_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/presets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Presets */
        get: operations["list_presets_api_presets_get"];
        put?: never;
        /** Create Preset */
        post: operations["create_preset_api_presets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/presets/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Import Preset
         * @description Import a ``.mcpreset.json``. A name clash gets " (2)", " (3)" ... appended.
         */
        post: operations["import_preset_api_presets_import_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/presets/{preset_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Preset */
        delete: operations["delete_preset_api_presets__preset_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/presets/{preset_id}/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Preset
         * @description The ``.mcpreset.json`` contents of a built-in or user preset.
         */
        get: operations["export_preset_api_presets__preset_id__export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Projects */
        get: operations["list_projects_api_projects_get"];
        put?: never;
        /** Create Project */
        post: operations["create_project_api_projects_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Project */
        get: operations["get_project_api_projects__project_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Project
         * @description Deletes the project and its caches/renders in the data folder. Your media is untouched.
         */
        delete: operations["delete_project_api_projects__project_id__delete"];
        options?: never;
        head?: never;
        /** Update Project */
        patch: operations["update_project_api_projects__project_id__patch"];
        trace?: never;
    };
    "/api/projects/{project_id}/clips": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Clips */
        get: operations["list_clips_api_projects__project_id__clips_get"];
        put?: never;
        /** Add Clip */
        post: operations["add_clip_api_projects__project_id__clips_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/cutlist": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Cutlist */
        get: operations["get_cutlist_api_projects__project_id__cutlist_get"];
        /**
         * Save Cutlist
         * @description Save an edited cutlist as a new version (the engine validates it first).
         */
        put: operations["save_cutlist_api_projects__project_id__cutlist_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/cutlist/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Versions */
        get: operations["list_versions_api_projects__project_id__cutlist_versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/cutlist/versions/{version}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Version */
        get: operations["get_version_api_projects__project_id__cutlist_versions__version__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Project Events
         * @description Server-Sent Events for the project's recent jobs: first their current state,
         *     then every change (the UI keeps this open). ``follow=false`` stops after the
         *     current state.
         */
        get: operations["project_events_api_projects__project_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/exports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Exports */
        get: operations["list_exports_api_projects__project_id__exports_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Jobs */
        get: operations["list_jobs_api_projects__project_id__jobs_get"];
        put?: never;
        /** Create Job */
        post: operations["create_job_api_projects__project_id__jobs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/nle-exports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Timeline
         * @description Write the edit for Final Cut / Resolve (FCPXML), Premiere (XML) or any NLE (EDL).
         */
        post: operations["export_timeline_api_projects__project_id__nle_exports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/timeline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Timeline
         * @description How every clip maps onto the timeline (for the players and waveforms).
         */
        get: operations["timeline_api_projects__project_id__timeline_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/system/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Liveness check (no token needed). The desktop app polls this after launch.
         */
        get: operations["health_api_system_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/system/info": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Info
         * @description ffmpeg, AI model and encoder availability. ``encoders=true`` test-encodes
         *     with each candidate encoder once (a few seconds, then cached).
         */
        get: operations["info_api_system_info_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/system/shutdown": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Shutdown
         * @description Stop this engine (the desktop app uses it to take over from a headless engine
         *     started by an NLE plugin). Refused while jobs run unless ``force``; only
         *     available when the engine has an API token.
         */
        post: operations["shutdown_api_system_shutdown_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AudioConfig */
        "AudioConfig-Input": {
            /** Gains Db */
            gains_db?: {
                [key: string]: number;
            };
            /** @default mix */
            mode?: components["schemas"]["AudioMode"];
            /** Single Clip Id */
            single_clip_id?: string | null;
        };
        /** AudioConfig */
        "AudioConfig-Output": {
            /** Gains Db */
            gains_db: {
                [key: string]: number;
            };
            /** @default mix */
            mode: components["schemas"]["AudioMode"];
            /** Single Clip Id */
            single_clip_id: string | null;
        };
        /**
         * AudioMode
         * @enum {string}
         */
        AudioMode: "mix" | "single";
        /** AudioTrack */
        "AudioTrack-Input": {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /**
             * Gain Db
             * @default 0
             */
            gain_db?: number;
            /** Index */
            index: number;
            /** Pieces */
            pieces: components["schemas"]["PlanPiece"][];
        };
        /** AudioTrack */
        "AudioTrack-Output": {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /**
             * Gain Db
             * @default 0
             */
            gain_db: number;
            /** Index */
            index: number;
            /** Pieces */
            pieces: components["schemas"]["PlanPiece"][];
        };
        /**
         * CameraLayout
         * @description One camera (clip), what kind of shot it is and who is visible in it.
         */
        "CameraLayout-Input": {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /**
             * Covers
             * @description Speaker ids in frame
             */
            covers?: string[];
            /**
             * Priority
             * @description User bias for this angle
             * @default 1
             */
            priority?: number;
            shot: components["schemas"]["ShotType"];
        };
        /**
         * CameraLayout
         * @description One camera (clip), what kind of shot it is and who is visible in it.
         */
        "CameraLayout-Output": {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /**
             * Covers
             * @description Speaker ids in frame
             */
            covers: string[];
            /**
             * Priority
             * @description User bias for this angle
             * @default 1
             */
            priority: number;
            shot: components["schemas"]["ShotType"];
        };
        /** ClipCreate */
        ClipCreate: {
            /**
             * Path
             * @description Absolute path; the file is referenced in place
             */
            path: string;
            /** @default speaker */
            role?: components["schemas"]["ClipRole"];
            /** Speaker Label */
            speaker_label?: string | null;
        };
        /** ClipOut */
        ClipOut: {
            file_status: components["schemas"]["FileStatus"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Reference */
            is_reference: boolean;
            media: components["schemas"]["MediaInfo"] | null;
            /** Name */
            name: string;
            /** Path */
            path: string;
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            role: components["schemas"]["ClipRole"];
            /** Speaker Label */
            speaker_label: string | null;
            sync: components["schemas"]["SyncResult"] | null;
        };
        /**
         * ClipRole
         * @enum {string}
         */
        ClipRole: "speaker" | "wide" | "broll" | "mic";
        /** ClipUpdate */
        ClipUpdate: {
            /**
             * Force
             * @description Relink even if the new file looks different
             * @default false
             */
            force?: boolean;
            /**
             * Path
             * @description Relink a moved file
             */
            path?: string | null;
            role?: components["schemas"]["ClipRole"] | null;
            /** Speaker Label */
            speaker_label?: string | null;
        };
        /** CutList */
        "CutList-Input": {
            audio?: components["schemas"]["AudioConfig-Input"];
            fps: components["schemas"]["Rational"];
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            /** Removals */
            removals?: components["schemas"]["Removal-Input"][];
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version?: 1;
            /** Segments */
            segments: components["schemas"]["Segment-Input"][];
            /**
             * Version
             * @description Edit revision; bumps on every change
             * @default 1
             */
            version?: number;
        };
        /** CutList */
        "CutList-Output": {
            audio: components["schemas"]["AudioConfig-Output"];
            fps: components["schemas"]["Rational"];
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            /** Removals */
            removals: components["schemas"]["Removal-Output"][];
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            /** Segments */
            segments: components["schemas"]["Segment-Output"][];
            /**
             * Version
             * @description Edit revision; bumps on every change
             * @default 1
             */
            version: number;
        };
        /** CutListIn */
        CutListIn: {
            cutlist: components["schemas"]["CutList-Input"];
        };
        /** CutListOut */
        CutListOut: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            cutlist: components["schemas"]["CutList-Output"];
            /** Source */
            source: string;
            /** Version */
            version: number;
        };
        /** CutListVersion */
        CutListVersion: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Segments */
            segments: number;
            /** Source */
            source: string;
            /** Version */
            version: number;
        };
        /** EditPlan */
        "EditPlan-Input": {
            /** @default mix */
            audio_mode?: components["schemas"]["AudioMode"];
            /** Audio Tracks */
            audio_tracks: components["schemas"]["AudioTrack-Input"][];
            /** Cutlist Version */
            cutlist_version: number;
            /** @default generic */
            host?: components["schemas"]["HostApp"];
            /** Markers */
            markers?: components["schemas"]["PlanMarker-Input"][];
            /** Media */
            media: components["schemas"]["PlanMedia-Input"][];
            /** @default stacked_enable */
            method?: components["schemas"]["PlanMethod"];
            /**
             * Plan Version
             * @default 1
             * @constant
             */
            plan_version?: 1;
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            /**
             * Removals
             * @description Approved only
             */
            removals?: components["schemas"]["PlanRemoval"][];
            sequence: components["schemas"]["PlanSequence-Input"];
            /** Video Events */
            video_events: components["schemas"]["VideoEvent-Input"][];
            /** Video Tracks */
            video_tracks: components["schemas"]["VideoTrack"][];
            /** Warnings */
            warnings?: string[];
        };
        /** EditPlan */
        "EditPlan-Output": {
            /** @default mix */
            audio_mode: components["schemas"]["AudioMode"];
            /** Audio Tracks */
            audio_tracks: components["schemas"]["AudioTrack-Output"][];
            /** Cutlist Version */
            cutlist_version: number;
            /** @default generic */
            host: components["schemas"]["HostApp"];
            /** Markers */
            markers: components["schemas"]["PlanMarker-Output"][];
            /** Media */
            media: components["schemas"]["PlanMedia-Output"][];
            /** @default stacked_enable */
            method: components["schemas"]["PlanMethod"];
            /**
             * Plan Version
             * @default 1
             * @constant
             */
            plan_version: 1;
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            /**
             * Removals
             * @description Approved only
             */
            removals: components["schemas"]["PlanRemoval"][];
            sequence: components["schemas"]["PlanSequence-Output"];
            /** Video Events */
            video_events: components["schemas"]["VideoEvent-Output"][];
            /** Video Tracks */
            video_tracks: components["schemas"]["VideoTrack"][];
            /** Warnings */
            warnings: string[];
        };
        /** ExportFileOut */
        ExportFileOut: {
            /** Cutlist Version */
            cutlist_version: number;
            /** Format */
            format: string;
            /** Path */
            path: string;
            /** Warnings */
            warnings: string[];
        };
        /** ExportOut */
        ExportOut: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Exists */
            exists: boolean;
            /** Frames */
            frames: number | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Job Id */
            job_id: string | null;
            /** Kind */
            kind: string;
            /** Path */
            path: string;
            /** Preset */
            preset: string | null;
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            /** Size Bytes */
            size_bytes: number | null;
        };
        /** FeedbackIn */
        FeedbackIn: {
            /** Note */
            note?: string | null;
            /** @description The editor's final timeline, read back from the host */
            plan: components["schemas"]["EditPlan-Input"];
        };
        /** FeedbackOut */
        FeedbackOut: {
            /** Cuts Auto */
            cuts_auto: number;
            /** Cuts Final */
            cuts_final: number;
            /**
             * Cuts Kept
             * @description Auto cuts the editor kept (within 2 frames)
             */
            cuts_kept: number;
            /** Path */
            path: string;
            /** Stored */
            stored: boolean;
        };
        /**
         * FileStatus
         * @enum {string}
         */
        FileStatus: "ok" | "missing" | "changed" | "unknown";
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** Handshake */
        Handshake: {
            /**
             * Api Version
             * @default 1.0.0
             */
            api_version?: string;
            /** Capabilities */
            capabilities: string[];
            /** Data Dir */
            data_dir: string;
            /** Engine Version */
            engine_version: string;
            licence: components["schemas"]["LicenceInfo"];
            models: components["schemas"]["ModelsAvailable"];
            /** Pid */
            pid: number;
        };
        /** Health */
        Health: {
            /**
             * Status
             * @default ok
             * @constant
             */
            status?: "ok";
            /** Version */
            version: string;
        };
        /**
         * HostApp
         * @enum {string}
         */
        HostApp: "premiere" | "resolve" | "fcp" | "generic";
        /** HostInfo */
        HostInfo: {
            app: components["schemas"]["HostApp"];
            /**
             * Os
             * @default
             * @enum {string}
             */
            os?: "mac" | "windows" | "linux" | "";
            /**
             * Version
             * @default
             */
            version?: string;
        };
        /** HostSequence */
        HostSequence: {
            fps: components["schemas"]["Rational"];
            /** Height */
            height: number;
            /** Name */
            name?: string | null;
            /** Width */
            width: number;
        };
        /** JobCreate */
        JobCreate: {
            kind: components["schemas"]["JobKind"];
            /** Params */
            params?: {
                [key: string]: unknown;
            };
        };
        /**
         * JobKind
         * @enum {string}
         */
        JobKind: "probe" | "sync" | "analyze" | "decide" | "auto" | "render" | "proxy" | "reframe";
        /** JobOut */
        JobOut: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Error */
            error: string | null;
            /** Finished At */
            finished_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            kind: components["schemas"]["JobKind"];
            /** Message */
            message: string;
            /** Params */
            params: {
                [key: string]: unknown;
            };
            /** Progress */
            progress: number;
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            /** Result */
            result: {
                [key: string]: unknown;
            } | null;
            /** Retry Of */
            retry_of: string | null;
            /** Stage */
            stage: string;
            /** Started At */
            started_at: string | null;
            status: components["schemas"]["JobStatus"];
        };
        /**
         * JobStatus
         * @enum {string}
         */
        JobStatus: "queued" | "running" | "succeeded" | "failed" | "cancelled";
        /** LicenceInfo */
        LicenceInfo: {
            /** Plan */
            plan?: string | null;
            /**
             * Status
             * @default dev
             * @enum {string}
             */
            status?: "dev" | "trial" | "active" | "expired" | "missing";
        };
        /**
         * MarkerColor
         * @enum {string}
         */
        MarkerColor: "red" | "yellow" | "green" | "blue";
        /**
         * MediaInfo
         * @description Facts about a source file, read with ffprobe (Phase 1).
         *
         *     Sound-only files (``has_video`` false) count frames at ``AUDIO_ONLY_FPS`` and
         *     have width = height = 0.
         */
        MediaInfo: {
            /**
             * Audio Channels
             * @default 0
             */
            audio_channels: number;
            /** Audio Codec */
            audio_codec: string | null;
            /** Audio Sample Rate */
            audio_sample_rate: number | null;
            /** Duration Frames */
            duration_frames: number;
            fps: components["schemas"]["Rational"];
            /**
             * Has Video
             * @default true
             */
            has_video: boolean;
            /** Height */
            height: number;
            /** Is Vfr */
            is_vfr: boolean;
            /**
             * Start Timecode
             * @description Embedded start timecode (HH:MM:SS:FF, ';' before FF = drop-frame)
             */
            start_timecode: string | null;
            /** Video Codec */
            video_codec: string;
            /** Width */
            width: number;
        };
        /** ModelsAvailable */
        ModelsAvailable: {
            /**
             * Asr
             * @default false
             */
            asr?: boolean;
            /** Face */
            face: boolean;
            /** Vad */
            vad: boolean;
        };
        /** NleExportIn */
        NleExportIn: {
            format: components["schemas"]["NleFormat"];
            /**
             * Output Path
             * @description Default: the exports folder
             */
            output_path?: string | null;
            /**
             * Version
             * @description Cutlist version; default latest
             */
            version?: number | null;
        };
        /** NleExportOut */
        NleExportOut: {
            export: components["schemas"]["ExportOut"];
            /** Warnings */
            warnings: string[];
        };
        /**
         * NleFormat
         * @enum {string}
         */
        NleFormat: "fcpxml" | "fcpxml_multicam" | "xmeml" | "edl";
        /** OutputSettings */
        OutputSettings: {
            fps: components["schemas"]["Rational"];
            /** Height */
            height: number;
            /** Width */
            width: number;
        };
        /** PlanMarker */
        "PlanMarker-Input": {
            /** @default yellow */
            color?: components["schemas"]["MarkerColor"];
            /**
             * Duration
             * @default 1
             */
            duration?: number;
            /** Frame */
            frame: number;
            /**
             * Kind
             * @default note
             * @enum {string}
             */
            kind?: "low_confidence" | "removal" | "note";
            /**
             * Note
             * @default
             */
            note?: string;
        };
        /** PlanMarker */
        "PlanMarker-Output": {
            /** @default yellow */
            color: components["schemas"]["MarkerColor"];
            /**
             * Duration
             * @default 1
             */
            duration: number;
            /** Frame */
            frame: number;
            /**
             * Kind
             * @default note
             * @enum {string}
             */
            kind: "low_confidence" | "removal" | "note";
            /**
             * Note
             * @default
             */
            note: string;
        };
        /**
         * PlanMedia
         * @description One source file (camera or recorder).
         */
        "PlanMedia-Input": {
            /**
             * Angle
             * @description 1-based multicam angle (cameras only)
             */
            angle: number | null;
            /** Audio Channels */
            audio_channels: number;
            /**
             * Audio Track
             * @description 1-based audio track, if its audio is used
             */
            audio_track: number | null;
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /**
             * Drift Ppm
             * @default 0
             */
            drift_ppm?: number;
            /**
             * Duration Frames
             * @description At the media's own frame rate
             */
            duration_frames: number;
            fps: components["schemas"]["Rational"];
            /** Has Audio */
            has_audio: boolean;
            /** Has Timecode */
            has_timecode: boolean;
            /** Height */
            height: number;
            /**
             * Host Ref
             * @description The host's id of this media item
             */
            host_ref?: string | null;
            /** Label */
            label: string;
            /** Name */
            name: string;
            /** Path */
            path: string;
            /**
             * Record Start Frame
             * @description Sequence frame where the media's first frame lands (< 0: starts before the sequence). Approximate under clock drift; pieces carry exact source times.
             */
            record_start_frame: number;
            /** Sample Rate */
            sample_rate: number;
            shot: components["schemas"]["ShotType"];
            /**
             * Start Timecode Frames
             * @description Embedded start timecode, own-rate frames
             */
            start_timecode_frames: number;
            /**
             * Video Track
             * @description 1-based track for stacked_enable
             */
            video_track: number | null;
            /** Width */
            width: number;
        };
        /**
         * PlanMedia
         * @description One source file (camera or recorder).
         */
        "PlanMedia-Output": {
            /**
             * Angle
             * @description 1-based multicam angle (cameras only)
             */
            angle: number | null;
            /** Audio Channels */
            audio_channels: number;
            /**
             * Audio Track
             * @description 1-based audio track, if its audio is used
             */
            audio_track: number | null;
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /**
             * Drift Ppm
             * @default 0
             */
            drift_ppm: number;
            /**
             * Duration Frames
             * @description At the media's own frame rate
             */
            duration_frames: number;
            fps: components["schemas"]["Rational"];
            /** Has Audio */
            has_audio: boolean;
            /** Has Timecode */
            has_timecode: boolean;
            /** Height */
            height: number;
            /**
             * Host Ref
             * @description The host's id of this media item
             */
            host_ref: string | null;
            /** Label */
            label: string;
            /** Name */
            name: string;
            /** Path */
            path: string;
            /**
             * Record Start Frame
             * @description Sequence frame where the media's first frame lands (< 0: starts before the sequence). Approximate under clock drift; pieces carry exact source times.
             */
            record_start_frame: number;
            /** Sample Rate */
            sample_rate: number;
            shot: components["schemas"]["ShotType"];
            /**
             * Start Timecode Frames
             * @description Embedded start timecode, own-rate frames
             */
            start_timecode_frames: number;
            /**
             * Video Track
             * @description 1-based track for stacked_enable
             */
            video_track: number | null;
            /** Width */
            width: number;
        };
        /**
         * PlanMethod
         * @enum {string}
         */
        PlanMethod: "cuts" | "stacked_enable" | "multicam";
        /**
         * PlanPiece
         * @description Sequence frames [start, end) show the media from ``source_in``.
         */
        PlanPiece: {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /** End */
            end: number;
            /**
             * Source In Frame
             * @description Frames at the media's own rate (nearest)
             */
            source_in_frame: number;
            /**
             * Source In Sample
             * @description Samples at the media's audio rate (nearest)
             */
            source_in_sample: number;
            /**
             * Source In Ticks
             * @description Premiere ticks (254016000000 per second)
             */
            source_in_ticks: number;
            /** Start */
            start: number;
        };
        /** PlanRemoval */
        PlanRemoval: {
            /** End */
            end: number;
            /** Kind */
            kind: string;
            /** Start */
            start: number;
        };
        /** PlanSequence */
        "PlanSequence-Input": {
            /** Duration Frames */
            duration_frames: number;
            fps: components["schemas"]["Rational"];
            /** Height */
            height: number;
            /**
             * Host Start Frame
             * @default 0
             */
            host_start_frame?: number;
            /** Name */
            name: string;
            /** Width */
            width: number;
        };
        /** PlanSequence */
        "PlanSequence-Output": {
            /** Duration Frames */
            duration_frames: number;
            fps: components["schemas"]["Rational"];
            /** Height */
            height: number;
            /**
             * Host Start Frame
             * @default 0
             */
            host_start_frame: number;
            /** Name */
            name: string;
            /** Width */
            width: number;
        };
        /** PlanSummary */
        PlanSummary: {
            /** Cutlist Version */
            cutlist_version: number;
            /** Cuts */
            cuts: number;
            /** Duration Frames */
            duration_frames: number;
            /** Low Confidence Cuts */
            low_confidence_cuts: number;
            /** Source */
            source: string;
        };
        /**
         * Preset
         * @enum {string}
         */
        Preset: "calm" | "balanced" | "dynamic" | "punchy";
        /**
         * PresetFile
         * @description Contents of a ``.mcpreset.json`` file (export / import).
         */
        "PresetFile-Input": {
            /**
             * Format
             * @default multicam-preset
             * @constant
             */
            format?: "multicam-preset";
            /** Name */
            name: string;
            settings: components["schemas"]["SwitchSettings-Input"];
            /**
             * Version
             * @default 1
             * @constant
             */
            version?: 1;
        };
        /**
         * PresetFile
         * @description Contents of a ``.mcpreset.json`` file (export / import).
         */
        "PresetFile-Output": {
            /**
             * Format
             * @default multicam-preset
             * @constant
             */
            format?: "multicam-preset";
            /** Name */
            name: string;
            settings: components["schemas"]["SwitchSettings-Output"];
            /**
             * Version
             * @default 1
             * @constant
             */
            version?: 1;
        };
        /** PresetOut */
        PresetOut: {
            /** Builtin */
            builtin: boolean;
            /**
             * Id
             * @description Built-in preset name, or the user preset's id
             */
            id: string;
            /** Name */
            name: string;
            settings: components["schemas"]["SwitchSettings-Output"];
        };
        /** ProjectCreate */
        ProjectCreate: {
            /** Name */
            name: string;
            /** @description Omit to follow the reference clip's frame rate and size */
            output?: components["schemas"]["OutputSettings"] | null;
            /** @default balanced */
            preset?: components["schemas"]["Preset"];
        };
        /**
         * ProjectLayout
         * @description Who is recorded by which mic, and who is visible in which camera.
         */
        ProjectLayout: {
            /**
             * Cameras
             * @description Clips without an entry are B-roll (never auto-selected)
             */
            cameras: components["schemas"]["CameraLayout-Input"][];
            /** Speakers */
            speakers: components["schemas"]["Speaker-Input"][];
        };
        /** ProjectOut */
        ProjectOut: {
            /**
             * Cameras
             * @description Effective layout of every clip
             */
            cameras: components["schemas"]["CameraLayout-Output"][];
            /** Clips */
            clips: components["schemas"]["ClipOut"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Cutlist Version */
            cutlist_version: number | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Layout Custom */
            layout_custom: boolean;
            /** Name */
            name: string;
            output: components["schemas"]["OutputSettings"];
            /** Output Custom */
            output_custom: boolean;
            preset: components["schemas"]["Preset"];
            /** Reference Clip Id */
            reference_clip_id: string | null;
            /**
             * Speakers
             * @description Effective speakers (explicit or from roles)
             */
            speakers: components["schemas"]["Speaker-Output"][];
            /** @description Effective switching settings */
            switch: components["schemas"]["SwitchSettings-Output"];
            /** Switch Custom */
            switch_custom: boolean;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** ProjectSummary */
        ProjectSummary: {
            /** Clip Count */
            clip_count: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Cutlist Version */
            cutlist_version: number | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            preset: components["schemas"]["Preset"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** ProjectUpdate */
        ProjectUpdate: {
            /** @description Explicit camera layout */
            layout?: components["schemas"]["ProjectLayout"] | null;
            /** Name */
            name?: string | null;
            output?: components["schemas"]["OutputSettings"] | null;
            /** @description Also drops custom switch settings unless 'switch' is given */
            preset?: components["schemas"]["Preset"] | null;
            /** Reference Clip Id */
            reference_clip_id?: string | null;
            /**
             * Reset Layout
             * @description Go back to the role-derived layout
             * @default false
             */
            reset_layout?: boolean;
            /** @description Custom switching (sliders / a user preset) */
            switch?: components["schemas"]["SwitchSettings-Input"] | null;
        };
        /**
         * Rational
         * @description An exact positive rational number, e.g. a frame rate of 30000/1001.
         */
        Rational: {
            /** Den */
            den: number;
            /** Num */
            num: number;
        };
        /**
         * Reframe
         * @description Crop/zoom for a segment. Normalized coordinates (0..1) of the crop centre.
         *
         *     The crop has the output's aspect ratio; ``scale`` 1 is the largest such crop
         *     (the full frame when source and output have the same shape), 2 shows half
         *     the width. With ``path`` the centre follows those keyframes (a slow pan that
         *     keeps a face framed); ``cx``/``cy`` are then the starting point.
         */
        "Reframe-Input": {
            /** Cx */
            cx: number;
            /** Cy */
            cy: number;
            /**
             * Manual
             * @description Set by the user: auto framing keeps it
             * @default false
             */
            manual?: boolean;
            /** Path */
            path?: components["schemas"]["ReframeKey"][] | null;
            /** Scale */
            scale: number;
        };
        /**
         * Reframe
         * @description Crop/zoom for a segment. Normalized coordinates (0..1) of the crop centre.
         *
         *     The crop has the output's aspect ratio; ``scale`` 1 is the largest such crop
         *     (the full frame when source and output have the same shape), 2 shows half
         *     the width. With ``path`` the centre follows those keyframes (a slow pan that
         *     keeps a face framed); ``cx``/``cy`` are then the starting point.
         */
        "Reframe-Output": {
            /** Cx */
            cx: number;
            /** Cy */
            cy: number;
            /**
             * Manual
             * @description Set by the user: auto framing keeps it
             * @default false
             */
            manual: boolean;
            /** Path */
            path: components["schemas"]["ReframeKey"][] | null;
            /** Scale */
            scale: number;
        };
        /**
         * ReframeKey
         * @description Crop centre at one timeline frame; the render moves linearly between keys.
         */
        ReframeKey: {
            /** Cx */
            cx: number;
            /** Cy */
            cy: number;
            /**
             * Frame
             * @description Timeline frame
             */
            frame: number;
        };
        /** Removal */
        "Removal-Input": {
            /**
             * Approved
             * @default false
             */
            approved?: boolean;
            /**
             * End Frame
             * @description Exclusive
             */
            end_frame: number;
            kind: components["schemas"]["RemovalKind"];
            /** Start Frame */
            start_frame: number;
        };
        /** Removal */
        "Removal-Output": {
            /**
             * Approved
             * @default false
             */
            approved: boolean;
            /**
             * End Frame
             * @description Exclusive
             */
            end_frame: number;
            kind: components["schemas"]["RemovalKind"];
            /** Start Frame */
            start_frame: number;
        };
        /**
         * RemovalKind
         * @enum {string}
         */
        RemovalKind: "filler" | "silence" | "manual";
        /** RoleIn */
        RoleIn: {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            role: components["schemas"]["ClipRole"];
            /** Speaker Label */
            speaker_label?: string | null;
        };
        /** RunIn */
        RunIn: {
            /**
             * Framing
             * @description Also auto-frame (faces, punch-ins)
             * @default false
             */
            framing?: boolean;
            /**
             * Steps
             * @description "auto" = everything; or exactly one step, e.g. ["decide"]
             * @default auto
             */
            steps?: "auto" | ("sync" | "analyze" | "decide" | "reframe")[];
            /**
             * Vad
             * @default auto
             * @enum {string}
             */
            vad?: "auto" | "silero" | "energy";
        };
        /** RunOut */
        RunOut: {
            /** Events Url */
            events_url: string;
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
            /** Kind */
            kind: string;
        };
        /** Segment */
        "Segment-Input": {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /**
             * Confidence
             * @description How sure auto-edit is about this cut
             */
            confidence?: number | null;
            /**
             * End Frame
             * @description Exclusive
             */
            end_frame: number;
            reframe?: components["schemas"]["Reframe-Input"] | null;
            /** @description Framing for 9:16 output (default: centred crop) */
            reframe_vertical?: components["schemas"]["Reframe-Input"] | null;
            /** @default auto */
            source?: components["schemas"]["SegmentSource"];
            /** Start Frame */
            start_frame: number;
        };
        /** Segment */
        "Segment-Output": {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /**
             * Confidence
             * @description How sure auto-edit is about this cut
             */
            confidence: number | null;
            /**
             * End Frame
             * @description Exclusive
             */
            end_frame: number;
            reframe: components["schemas"]["Reframe-Output"] | null;
            /** @description Framing for 9:16 output (default: centred crop) */
            reframe_vertical: components["schemas"]["Reframe-Output"] | null;
            /** @default auto */
            source: components["schemas"]["SegmentSource"];
            /** Start Frame */
            start_frame: number;
        };
        /**
         * SegmentSource
         * @enum {string}
         */
        SegmentSource: "auto" | "manual";
        /**
         * SessionClipIn
         * @description A clip as the host sees it. Frames are at the host *sequence* rate.
         */
        SessionClipIn: {
            /** Audio Channels */
            audio_channels?: number | null;
            /** Host Ref */
            host_ref?: string | null;
            /**
             * In Frame
             * @description Media offset of the clip item's first frame
             * @default 0
             */
            in_frame?: number;
            /**
             * Kind
             * @description audio = a sound-only mic / recorder track
             * @default video
             * @enum {string}
             */
            kind?: "video" | "audio";
            /** Label */
            label?: string | null;
            /** Out Frame */
            out_frame?: number | null;
            /** Path */
            path: string;
            /**
             * Record Start Frame
             * @description Sequence frame where the clip item starts
             * @default 0
             */
            record_start_frame?: number;
            /** Track */
            track?: number | null;
        };
        /** SessionClipOut */
        SessionClipOut: {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            file_status: components["schemas"]["FileStatus"];
            /** Host Ref */
            host_ref: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "video" | "audio";
            /** Label */
            label: string | null;
            /** Name */
            name: string;
            /** Path */
            path: string;
            role: components["schemas"]["ClipRole"];
            /** Sync Confidence */
            sync_confidence: number | null;
            /** Synced */
            synced: boolean;
            /** Track */
            track: number | null;
        };
        /** SessionCreate */
        SessionCreate: {
            /**
             * Already Synced
             * @description Clips come from a synced sequence: skip audio sync
             * @default false
             */
            already_synced?: boolean;
            /** Clips */
            clips: components["schemas"]["SessionClipIn"][];
            host: components["schemas"]["HostInfo"];
            /**
             * Host Sequence Id
             * @description Re-sending the same id reuses the session
             */
            host_sequence_id?: string | null;
            sequence: components["schemas"]["HostSequence"];
        };
        /** SessionOut */
        SessionOut: {
            /** Already Synced */
            already_synced: boolean;
            /** Cameras */
            cameras: components["schemas"]["CameraLayout-Output"][];
            /** Clips */
            clips: components["schemas"]["SessionClipOut"][];
            host: components["schemas"]["HostInfo"];
            /** Host Sequence Id */
            host_sequence_id: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            job: components["schemas"]["JobOut"] | null;
            /** Layout Custom */
            layout_custom: boolean;
            method: components["schemas"]["PlanMethod"];
            /** Name */
            name: string;
            plan: components["schemas"]["PlanSummary"] | null;
            preset: components["schemas"]["Preset"];
            /**
             * Project Id
             * Format: uuid
             */
            project_id: string;
            /**
             * Reused
             * @default false
             */
            reused?: boolean;
            /** Speakers */
            speakers: components["schemas"]["Speaker-Output"][];
            state: components["schemas"]["SessionState"];
            switch: components["schemas"]["SwitchSettings-Output"];
            /** Switch Custom */
            switch_custom: boolean;
            /** Warnings */
            warnings: string[];
        };
        /** SessionSetup */
        SessionSetup: {
            layout?: components["schemas"]["ProjectLayout"] | null;
            method?: components["schemas"]["PlanMethod"] | null;
            /** Name */
            name?: string | null;
            preset?: components["schemas"]["Preset"] | null;
            /**
             * Reset Layout
             * @default false
             */
            reset_layout?: boolean;
            /**
             * Roles
             * @description Quick setup: a role (+ name) per clip
             */
            roles?: components["schemas"]["RoleIn"][] | null;
            switch?: components["schemas"]["SwitchSettings-Input"] | null;
        };
        /**
         * SessionState
         * @enum {string}
         */
        SessionState: "setup" | "running" | "ready" | "failed";
        /**
         * ShotType
         * @description What a camera shows. Switching understands every layout (D74).
         * @enum {string}
         */
        ShotType: "solo" | "two" | "three" | "four" | "wide" | "broll";
        /** SocialIn */
        SocialIn: {
            /** Aspects */
            aspects: ("16:9" | "4:5" | "9:16" | "1:1")[];
            /** In Frame */
            in_frame: number;
            /** Out Frame */
            out_frame: number;
        };
        /**
         * Speaker
         * @description A person in the recording and the mic that hears them best.
         */
        "Speaker-Input": {
            /**
             * Id
             * Format: uuid
             */
            id?: string;
            /**
             * Mic Channel
             * @description Channel of the mic in a multi-channel file
             */
            mic_channel?: number | null;
            /**
             * Mic Clip Id
             * @description Clip whose audio is this person's mic; None: single-mic mode
             */
            mic_clip_id?: string | null;
            /** Name */
            name: string;
        };
        /**
         * Speaker
         * @description A person in the recording and the mic that hears them best.
         */
        "Speaker-Output": {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Mic Channel
             * @description Channel of the mic in a multi-channel file
             */
            mic_channel: number | null;
            /**
             * Mic Clip Id
             * @description Clip whose audio is this person's mic; None: single-mic mode
             */
            mic_clip_id: string | null;
            /** Name */
            name: string;
        };
        /**
         * SwitchSettings
         * @description ``SwitchParams`` as a validated, serialisable model (user presets, API).
         */
        "SwitchSettings-Input": {
            /** Bridge Gap S */
            bridge_gap_s: number;
            /** Crosstalk To Wide S */
            crosstalk_to_wide_s: number;
            /**
             * Group Reward
             * @default 0.7
             */
            group_reward?: number;
            /** Lead S */
            lead_s: number;
            /**
             * Max Shot S
             * @description 0 = no limit
             * @default 0
             */
            max_shot_s?: number;
            /** Min Shot S */
            min_shot_s: number;
            /** Silence To Wide S */
            silence_to_wide_s: number;
            /** Switch Delay S */
            switch_delay_s: number;
            /**
             * Wide Frequency
             * @default 0.3
             */
            wide_frequency?: number;
        };
        /**
         * SwitchSettings
         * @description ``SwitchParams`` as a validated, serialisable model (user presets, API).
         */
        "SwitchSettings-Output": {
            /** Bridge Gap S */
            bridge_gap_s: number;
            /** Crosstalk To Wide S */
            crosstalk_to_wide_s: number;
            /**
             * Group Reward
             * @default 0.7
             */
            group_reward: number;
            /** Lead S */
            lead_s: number;
            /**
             * Max Shot S
             * @description 0 = no limit
             * @default 0
             */
            max_shot_s: number;
            /** Min Shot S */
            min_shot_s: number;
            /** Silence To Wide S */
            silence_to_wide_s: number;
            /** Switch Delay S */
            switch_delay_s: number;
            /**
             * Wide Frequency
             * @default 0.3
             */
            wide_frequency: number;
        };
        /**
         * SyncResult
         * @description How a clip lines up with the project's reference clip.
         *
         *     Sign convention (shared with ``benchmark.GroundTruth``):
         *         ``offset_samples`` = position of an event in THIS clip
         *                              minus position of the same event in the REFERENCE clip.
         *         Positive  -> this clip started recording EARLIER than the reference.
         *         Negative  -> this clip started recording LATER than the reference.
         *
         *     ``drift_ppm``: how much faster this clip's clock runs than the reference,
         *     in parts per million. A value of +100 means the clip accumulates 0.36 s
         *     of extra duration per hour. This is a model parameter, not a timeline
         *     position, so a float is acceptable here.
         */
        SyncResult: {
            /** Confidence */
            confidence: number;
            /**
             * Drift Ppm
             * @default 0
             */
            drift_ppm: number;
            /** Offset Samples */
            offset_samples: number;
            /**
             * Reference Clip Id
             * Format: uuid
             */
            reference_clip_id: string;
            /** Sample Rate */
            sample_rate: number;
        };
        /** SystemInfo */
        SystemInfo: {
            /** Api Version */
            api_version: string;
            /** Data Dir */
            data_dir: string;
            /**
             * Encoders H264
             * @description None until requested with ?encoders=true
             */
            encoders_h264: string[] | null;
            /** Encoders Hevc */
            encoders_hevc: string[] | null;
            /** Engine Version */
            engine_version: string;
            /** Face Model Available */
            face_model_available: boolean;
            /** Ffmpeg */
            ffmpeg: string | null;
            /** Ffmpeg Version */
            ffmpeg_version: string | null;
            /** Render Presets */
            render_presets: string[];
            /** Vad Model Available */
            vad_model_available: boolean;
        };
        /**
         * TimelineClip
         * @description How a clip maps onto the timeline, for players and waveforms in the editor.
         *
         *     At timeline time ``t`` (seconds) the clip shows media time
         *     ``t * speed + media_offset_s`` (seconds from the start of the file / proxy)
         *     and plays audio sample position ``(t * speed + audio_offset_s) * rate``.
         */
        TimelineClip: {
            /** Audio Offset S */
            audio_offset_s: number;
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /** Duration S */
            duration_s: number;
            fps: components["schemas"]["Rational"];
            /** Has Audio */
            has_audio: boolean;
            /** Has Proxy */
            has_proxy: boolean;
            /** Height */
            height: number;
            /** Media Offset S */
            media_offset_s: number;
            /** Speed */
            speed: number;
            /**
             * Width
             * @description Picture size as displayed (after rotation)
             */
            width: number;
        };
        /** TimelineOut */
        TimelineOut: {
            /** Clips */
            clips: components["schemas"]["TimelineClip"][];
            /**
             * Duration Frames
             * @description Length of the latest cutlist, if any
             */
            duration_frames: number | null;
            fps: components["schemas"]["Rational"];
            /**
             * Proxies Ready
             * @description Every clip has a preview copy
             */
            proxies_ready: boolean;
        };
        /** TrackPiece */
        TrackPiece: {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /**
             * Enabled
             * @description Live at this time (stacked_enable)
             */
            enabled: boolean;
            /** End */
            end: number;
            /**
             * Source In Frame
             * @description Frames at the media's own rate (nearest)
             */
            source_in_frame: number;
            /**
             * Source In Sample
             * @description Samples at the media's audio rate (nearest)
             */
            source_in_sample: number;
            /**
             * Source In Ticks
             * @description Premiere ticks (254016000000 per second)
             */
            source_in_ticks: number;
            /** Start */
            start: number;
        };
        /** UserPresetIn */
        UserPresetIn: {
            /** Name */
            name: string;
            settings: components["schemas"]["SwitchSettings-Input"];
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /**
         * VideoEvent
         * @description A piece of the live edit (what the viewer sees).
         */
        "VideoEvent-Input": {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /** Confidence */
            confidence?: number | null;
            /** End */
            end: number;
            reframe?: components["schemas"]["Reframe-Input"] | null;
            reframe_vertical?: components["schemas"]["Reframe-Input"] | null;
            shot: components["schemas"]["ShotType"];
            /**
             * Source In Frame
             * @description Frames at the media's own rate (nearest)
             */
            source_in_frame: number;
            /**
             * Source In Sample
             * @description Samples at the media's audio rate (nearest)
             */
            source_in_sample: number;
            /**
             * Source In Ticks
             * @description Premiere ticks (254016000000 per second)
             */
            source_in_ticks: number;
            /** Start */
            start: number;
        };
        /**
         * VideoEvent
         * @description A piece of the live edit (what the viewer sees).
         */
        "VideoEvent-Output": {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /** Confidence */
            confidence: number | null;
            /** End */
            end: number;
            reframe: components["schemas"]["Reframe-Output"] | null;
            reframe_vertical: components["schemas"]["Reframe-Output"] | null;
            shot: components["schemas"]["ShotType"];
            /**
             * Source In Frame
             * @description Frames at the media's own rate (nearest)
             */
            source_in_frame: number;
            /**
             * Source In Sample
             * @description Samples at the media's audio rate (nearest)
             */
            source_in_sample: number;
            /**
             * Source In Ticks
             * @description Premiere ticks (254016000000 per second)
             */
            source_in_ticks: number;
            /** Start */
            start: number;
        };
        /** VideoTrack */
        VideoTrack: {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /** Index */
            index: number;
            /** Pieces */
            pieces: components["schemas"]["TrackPiece"][];
        };
        /** WaveformOut */
        WaveformOut: {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /**
             * Peaks
             * @description Base64 bytes, one per bucket: 0 = silence .. 255 = full scale
             */
            peaks: string;
            /**
             * Rate
             * @description Values per second of audio
             */
            rate: number;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    get_clip_api_clips__clip_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                clip_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ClipOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_clip_api_clips__clip_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                clip_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_clip_api_clips__clip_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                clip_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ClipUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ClipOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    clip_proxy_api_clips__clip_id__proxy_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                clip_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    clip_waveform_api_clips__clip_id__waveform_get: {
        parameters: {
            query?: {
                rate?: number;
            };
            header?: never;
            path: {
                clip_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WaveformOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_export_api_exports__export_id__delete: {
        parameters: {
            query?: {
                delete_file?: boolean;
            };
            header?: never;
            path: {
                export_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_export_api_exports__export_id__file_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                export_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_job_api_jobs__job_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_job_api_jobs__job_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    job_events_api_jobs__job_id__events_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    retry_job_api_jobs__job_id__retry_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    handshake_api_plugin_v1_handshake_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Handshake"];
                };
            };
        };
    };
    list_presets_api_plugin_v1_presets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PresetOut"][];
                };
            };
        };
    };
    create_preset_api_plugin_v1_presets_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserPresetIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PresetOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_session_api_plugin_v1_sessions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SessionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_session_api_plugin_v1_sessions__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_editplan_api_plugin_v1_sessions__session_id__editplan_get: {
        parameters: {
            query?: {
                host?: components["schemas"]["HostApp"];
                version?: number | null;
                method?: components["schemas"]["PlanMethod"] | null;
            };
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EditPlan-Output"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    session_events_api_plugin_v1_sessions__session_id__events_get: {
        parameters: {
            query?: {
                job_id?: string | null;
            };
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_session_api_plugin_v1_sessions__session_id__export_get: {
        parameters: {
            query?: {
                format?: string;
                version?: number | null;
                method?: components["schemas"]["PlanMethod"] | null;
            };
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExportFileOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    feedback_api_plugin_v1_sessions__session_id__feedback_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FeedbackIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeedbackOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    run_session_api_plugin_v1_sessions__session_id__run_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RunIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    setup_session_api_plugin_v1_sessions__session_id__setup_patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SessionSetup"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    social_clips_api_plugin_v1_sessions__session_id__social_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SocialIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_presets_api_presets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PresetOut"][];
                };
            };
        };
    };
    create_preset_api_presets_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserPresetIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PresetOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    import_preset_api_presets_import_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PresetFile-Input"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PresetOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_preset_api_presets__preset_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                preset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_preset_api_presets__preset_id__export_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                preset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PresetFile-Output"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_projects_api_projects_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectSummary"][];
                };
            };
        };
    };
    create_project_api_projects_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_api_projects__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_project_api_projects__project_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_project_api_projects__project_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_clips_api_projects__project_id__clips_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ClipOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_clip_api_projects__project_id__clips_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ClipCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ClipOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_cutlist_api_projects__project_id__cutlist_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CutListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    save_cutlist_api_projects__project_id__cutlist_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CutListIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CutListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_versions_api_projects__project_id__cutlist_versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CutListVersion"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_version_api_projects__project_id__cutlist_versions__version__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
                version: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CutListOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    project_events_api_projects__project_id__events_get: {
        parameters: {
            query?: {
                follow?: boolean;
            };
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_exports_api_projects__project_id__exports_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExportOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_jobs_api_projects__project_id__jobs_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_job_api_projects__project_id__jobs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["JobCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_timeline_api_projects__project_id__nle_exports_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NleExportIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NleExportOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    timeline_api_projects__project_id__timeline_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TimelineOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_api_system_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
        };
    };
    info_api_system_info_get: {
        parameters: {
            query?: {
                encoders?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemInfo"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    shutdown_api_system_shutdown_post: {
        parameters: {
            query?: {
                force?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: boolean;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
