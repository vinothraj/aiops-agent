import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface LogResponse {
  id: number;
  timestamp: string;
  service_name: string;
  log_level: string;
  message: string;
  stacktrace?: string;
  file_name: string;
  file_path: string;
  created_at: string;
}

export interface LogFileResponse {
  id: number;
  file_name: string;
  file_path: string;
  service_name: string;
  last_processed_position: number;
  last_processed_time?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface LogStatsSummary {
  total_logs: number;
  error_logs: number;
  warning_logs: number;
  services: number;
}

export interface RCAStructuredResponse {
  incident_type: string;
  root_cause_category: string;
  root_cause: string;
  severity: string;
  business_impact: string;
  technical_impact: string;
  affected_services: string[];
  affected_dependencies: string[];
  pattern_detected: string[];
  deployment_related: boolean;
  recommended_action: string;
  immediate_fix: string;
  short_term_fix: string;
  long_term_fix: string;
  incident_recommendation: string;
  confidence_score: number;
  severity_confidence: number;
  recommendation_confidence: number;
  summary: string;
}

export interface LogAnalysisResponse {
  id: number;
  log_id: number;
  root_cause: string;
  root_cause_category: string;
  severity: string;
  business_impact?: string;
  technical_impact?: string;
  confidence_score: number;
  recommendation?: string;
  summary?: string;
  created_at: string;
  patterns: any[];
  dependencies: any[];
  services: any[];
  rca_detail?: RCAStructuredResponse;
}

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  // We point to localhost:8000 by default, or relative path if deployed on the same server
  private baseUrl = 'http://localhost:8000/api';

  constructor(private http: HttpClient) {}

  getStatsSummary(): Observable<LogStatsSummary> {
    return this.http.get<LogStatsSummary>(`${this.baseUrl}/stats/summary`);
  }

  getLogs(filters: {
    service_name?: string;
    log_level?: string;
    start_date?: string;
    end_date?: string;
    search_query?: string;
    skip?: number;
    limit?: number;
  }): Observable<LogResponse[]> {
    let params = new HttpParams();
    if (filters.service_name) params = params.set('service_name', filters.service_name);
    if (filters.log_level) params = params.set('log_level', filters.log_level);
    if (filters.start_date) params = params.set('start_date', filters.start_date);
    if (filters.end_date) params = params.set('end_date', filters.end_date);
    if (filters.search_query) params = params.set('search_query', filters.search_query);
    if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
    if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());

    return this.http.get<LogResponse[]>(`${this.baseUrl}/logs`, { params });
  }

  searchLogs(q: string, skip = 0, limit = 100): Observable<LogResponse[]> {
    let params = new HttpParams().set('q', q);
    params = params.set('skip', skip.toString());
    params = params.set('limit', limit.toString());
    return this.http.get<LogResponse[]>(`${this.baseUrl}/logs/search`, { params });
  }

  getLogSources(): Observable<LogFileResponse[]> {
    return this.http.get<LogFileResponse[]>(`${this.baseUrl}/log-sources`);
  }

  reprocessLogs(fileId?: number, filePath?: string): Observable<any> {
    const body: any = {};
    if (fileId !== undefined) body.file_id = fileId;
    if (filePath !== undefined) body.file_path = filePath;
    return this.http.post<any>(`${this.baseUrl}/logs/reprocess`, body);
  }

  triggerRcaAnalysis(logId: number): Observable<LogAnalysisResponse> {
    return this.http.post<LogAnalysisResponse>(`${this.baseUrl}/rca/analyze/${logId}`, {});
  }

  getRcaAnalysis(logId: number): Observable<LogAnalysisResponse> {
    return this.http.get<LogAnalysisResponse>(`${this.baseUrl}/rca/analysis/${logId}`);
  }

  getAllRcaAnalyses(skip = 0, limit = 50): Observable<LogAnalysisResponse[]> {
    let params = new HttpParams();
    params = params.set('skip', skip.toString());
    params = params.set('limit', limit.toString());
    return this.http.get<LogAnalysisResponse[]>(`${this.baseUrl}/rca/analyses`, { params });
  }

  // ─── Incident Triage ──────────────────────────────────────────────────

  triggerTriage(logId: number): Observable<IncidentDecisionResponse> {
    return this.http.post<IncidentDecisionResponse>(`${this.baseUrl}/incident/triage`, { log_id: logId });
  }

  getIncidents(filters?: { priority?: string; status?: string; skip?: number; limit?: number }): Observable<IncidentDecisionResponse[]> {
    let params = new HttpParams();
    if (filters?.priority) params = params.set('priority', filters.priority);
    if (filters?.status) params = params.set('status', filters.status);
    if (filters?.skip !== undefined) params = params.set('skip', filters.skip.toString());
    if (filters?.limit !== undefined) params = params.set('limit', filters.limit.toString());
    return this.http.get<IncidentDecisionResponse[]>(`${this.baseUrl}/incidents`, { params });
  }

  getIncident(id: number): Observable<IncidentDecisionResponse> {
    return this.http.get<IncidentDecisionResponse>(`${this.baseUrl}/incidents/${id}`);
  }

  // ─── GitLab Integration ───────────────────────────────────────────────

  getGitlabIssues(): Observable<GitlabIssueResponse[]> {
    return this.http.get<GitlabIssueResponse[]>(`${this.baseUrl}/gitlab/issues`);
  }

  syncGitlabIssues(): Observable<GitlabIssueResponse[]> {
    return this.http.post<GitlabIssueResponse[]>(`${this.baseUrl}/gitlab/sync`, {});
  }

  // ─── Notification & Timeline Integration ───────────────────────────────

  getNotifications(filters?: { channel?: string; status?: string; skip?: number; limit?: number }): Observable<NotificationResponse[]> {
    let params = new HttpParams();
    if (filters?.channel) params = params.set('channel', filters.channel);
    if (filters?.status) params = params.set('status', filters.status);
    if (filters?.skip !== undefined) params = params.set('skip', filters.skip.toString());
    if (filters?.limit !== undefined) params = params.set('limit', filters.limit.toString());
    return this.http.get<NotificationResponse[]>(`${this.baseUrl}/notifications`, { params });
  }

  getNotificationRecipientList(): Observable<NotificationRecipient[]> {
    return this.http.get<NotificationRecipient[]>(`${this.baseUrl}/notifications/recipients/list`);
  }

  createNotificationRecipient(recipient: Omit<NotificationRecipient, 'id'>): Observable<NotificationRecipient> {
    return this.http.post<NotificationRecipient>(`${this.baseUrl}/notifications/recipients`, recipient);
  }

  updateNotificationRecipient(id: number, recipient: Omit<NotificationRecipient, 'id'>): Observable<NotificationRecipient> {
    return this.http.put<NotificationRecipient>(`${this.baseUrl}/notifications/recipients/${id}`, recipient);
  }

  deleteNotificationRecipient(id: number): Observable<any> {
    return this.http.delete<any>(`${this.baseUrl}/notifications/recipients/${id}`);
  }

  getDailyDigest(): Observable<{ digest: string }> {
    return this.http.get<{ digest: string }>(`${this.baseUrl}/notifications/digest`);
  }

  getWeeklyInsights(): Observable<{ insights: string }> {
    return this.http.get<{ insights: string }>(`${this.baseUrl}/notifications/insights`);
  }

  testNotification(payload: { channel: string; destination: string }): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/notifications/test`, payload);
  }

  retryNotification(id: number): Observable<NotificationResponse> {
    return this.http.post<NotificationResponse>(`${this.baseUrl}/notifications/retry/${id}`, {});
  }

  getIncidentTimeline(incidentId: number): Observable<TimelineEventResponse[]> {
    return this.http.get<TimelineEventResponse[]>(`${this.baseUrl}/notifications/timeline/${incidentId}`);
  }
}

export interface IncidentDecisionResponse {
  id: number;
  log_id: number;
  analysis_id?: number;
  risk_score: number;
  business_impact_score: number;
  technical_impact_score: number;
  frequency_score: number;
  priority: string;
  recommended_action: string;
  rationale: string;
  affected_services?: string;
  similar_incident_count: number;
  gitlab_issue_id?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface IssueActivityResponse {
  id: number;
  gitlab_issue_id: number;
  action_type: string;
  description: string;
  timestamp: string;
}

export interface GitlabIssueResponse {
  id: number;
  incident_decision_id: number;
  gitlab_issue_id: number;
  gitlab_issue_iid: number;
  web_url: string;
  title: string;
  state: string;
  assignee?: string;
  labels?: string;
  created_at: string;
  updated_at: string;
  activities: IssueActivityResponse[];
}

export interface NotificationResponse {
  id: number;
  incident_decision_id?: number;
  channel: string;
  recipient_destination: string;
  title: string;
  message: string;
  status: string;
  retry_count: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface NotificationRecipient {
  id: number;
  category: string;
  channel: string;
  destination: string;
  recipient_name: string;
  is_active: boolean;
}

export interface TimelineEventResponse {
  timestamp: string;
  event_type: string;
  title: string;
  description: string;
  status?: string;
  meta?: any;
}
