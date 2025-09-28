export interface PRReviewRequest {
  pr_url: string;
  github_token: string;
}

export interface PRInfo {
  title: string;
  author: string;
  branch: string;
  files_changed: number;
}

export interface ReviewComment {
  line: number;
  message: string;
  severity: string;
  type: string;
  suggestion?: string;
  file?: string;
  source_agent?: string;
}

export interface PRReviewResponse {
  summary: string;
  final_status: string;
  timestamp: string;
  pr_info: PRInfo;
  execution_time: number;
  comments: ReviewComment[];
  agents?: { [key: string]: string[] }; // deprecated
}

export type AgentName = 'CodeQuality' | 'BugDetection' | 'Security' | 'Dependency' | 'Documentation';

export interface AgentConfig {
  icon: React.ReactNode;
  color: string;
  border: string;
}

export type StatusType = 'approve' | 'needs changes' | 'error';