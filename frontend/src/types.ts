export type Mode = 'checksum' | 'original';
export type Step = 0 | 1 | 2 | 3;
export interface Source {
  source_id?: string;
  root_name: string;
  files: number;
  total_bytes: number;
}
export interface Destination {
  connection_id?: string;
  version: string;
  asset_count: number;
  known_bytes: number;
  unknown_sizes: number;
  issues: unknown[];
}
export interface EmbeddedVideo {
  offset: number;
  size: number;
  sha256: string;
  sha1?: string;
  mime?: string;
  container?: string;
  validated: boolean;
  evidence?: string[];
}
export interface MediaProof {
  family: 'image' | 'video' | 'unknown';
  mime?: string | null;
  container?: string | null;
  evidence?: string[];
  complete: boolean;
  valid: boolean;
  issues?: string[];
  embedded_video?: EmbeddedVideo;
  motion_photo?: { declared: boolean; validated: boolean; format?: string; issues?: string[] };
}
export interface DateProvenance {
  method: string;
  semantics?: string;
  timezone?: string;
  capture_instant_verified?: boolean;
  source_paths?: string[];
  fields?: unknown;
}
export interface Finding {
  kind: string;
  status: string;
  evidence: string;
  path: string;
  asset_ids: string[];
  message: string;
  source_sha256?: string;
  source_sha1?: string;
  size?: number;
  destination_sha256?: Record<string, string>;
  source_occurrences?: number;
  sidecars?: string[];
  source_date?: string;
  date_kind?: string;
  source_date_provenance?: DateProvenance;
  destination_dates?: Record<string, string | null>;
  classification?: string;
  content_state?: string;
  album_ids?: string[];
  source_media?: MediaProof;
  source_filename_mime?: string | null;
  expected_type?: string | null;
  destination_types?: Record<string, string | null>;
  destination_media?: Record<string, MediaProof>;
  mismatched_asset_ids?: string[];
  unknown_asset_ids?: string[];
  proof_level?: string;
  relation?: string;
  image_asset_ids?: string[];
  video_asset_ids?: string[];
  source_video_paths?: string[];
  expected_video_sha256?: string;
  expected_video_sha1?: string | null;
  expected_video_size?: number;
  embedded_video_offset?: number;
  destination_video_sha256?: string;
  destination_links?: Record<string, string | null>;
  reverse_links?: Record<string, string>;
}
export interface Report {
  schema_version: number;
  mode: Mode;
  immich_version: string;
  scope: string;
  coverage?: {
    capture_dates: { comparable: number; total: number; asserted?: number; agreements?: number; differences?: number; unresolved?: number; container_only?: number };
    container_dates?: { total: number; comparable: number; agreements: number; differences: number; unresolved: number; policy: string };
    album_membership: { asserted_occurrences: number; total: number; policy: string };
    media_types?: { total: number; matched: number; checked: number; agreements: number; differences: number; unresolved: number; unmatched: number };
    paired_media?: { asserted: number; source_pairs: number; standalone_companions: number; original_verified: number; checksum_supported: number; differences: number; unresolved: number; total: number };
  };
  summary: {
    source_files: number;
    source_bytes: number;
    inventory_files?: number;
    inventory_bytes?: number;
    media_files?: number;
    auxiliary_files?: number;
    auxiliary_bytes?: number;
    sidecar_files?: number;
    album_metadata_files?: number;
    unique_source_content: number;
    destination_assets: number;
    matched: number;
    attention: number;
    content_counts: Record<string, number>;
    coverage_complete: boolean;
    verification: string;
    source_albums: number;
    destination_albums: number;
  };
  limitations: string[];
  findings: Finding[];
}
export interface Job {
  id: string;
  status: 'running' | 'cancelled' | 'interrupted' | 'completed' | 'failed';
  phase: string;
  progress: Record<string, number | string>;
  report: Report | null;
  error: string | null;
  mode: Mode;
  demo: boolean;
  demo_scenario?: 'problems' | 'correct';
  created_at?: string;
}
