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
        ClipRole: "speaker" | "wide" | "broll";
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
        JobKind: "probe" | "sync" | "analyze" | "decide" | "auto" | "render";
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
        /**
         * MediaInfo
         * @description Facts about a source file, read with ffprobe (Phase 1).
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
            /** Height */
            height: number;
            /** Is Vfr */
            is_vfr: boolean;
            /** Video Codec */
            video_codec: string;
            /** Width */
            width: number;
        };
        /** OutputSettings */
        OutputSettings: {
            fps: components["schemas"]["Rational"];
            /** Height */
            height: number;
            /** Width */
            width: number;
        };
        /**
         * Preset
         * @enum {string}
         */
        Preset: "calm" | "balanced" | "dynamic";
        /** ProjectCreate */
        ProjectCreate: {
            /** Name */
            name: string;
            /** @description Omit to follow the reference clip's frame rate and size */
            output?: components["schemas"]["OutputSettings"] | null;
            /** @default balanced */
            preset?: components["schemas"]["Preset"];
        };
        /** ProjectOut */
        ProjectOut: {
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
            /** Name */
            name: string;
            output: components["schemas"]["OutputSettings"];
            /** Output Custom */
            output_custom: boolean;
            preset: components["schemas"]["Preset"];
            /** Reference Clip Id */
            reference_clip_id: string | null;
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
            /** Name */
            name?: string | null;
            output?: components["schemas"]["OutputSettings"] | null;
            preset?: components["schemas"]["Preset"] | null;
            /** Reference Clip Id */
            reference_clip_id?: string | null;
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
         * @description Crop/zoom for a segment. Normalized coordinates (0..1) of the crop center.
         */
        Reframe: {
            /** Cx */
            cx: number;
            /** Cy */
            cy: number;
            /** Scale */
            scale: number;
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
        /** Segment */
        "Segment-Input": {
            /**
             * Clip Id
             * Format: uuid
             */
            clip_id: string;
            /**
             * End Frame
             * @description Exclusive
             */
            end_frame: number;
            reframe?: components["schemas"]["Reframe"] | null;
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
             * End Frame
             * @description Exclusive
             */
            end_frame: number;
            reframe: components["schemas"]["Reframe"] | null;
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
            /** Ffmpeg */
            ffmpeg: string | null;
            /** Ffmpeg Version */
            ffmpeg_version: string | null;
            /** Render Presets */
            render_presets: string[];
            /** Vad Model Available */
            vad_model_available: boolean;
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
}
