import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, LogResponse, LogFileResponse, LogAnalysisResponse, LogSummaryResponse, LogQueryFilters, DiagnoseCodebaseResponse, AskAiResponse } from '../../services/api.service';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

const LEVEL_COLORS: { [level: string]: string } = {
  ERROR: 'var(--color-error)',
  WARNING: 'var(--color-warning)',
  INFO: 'var(--color-info)',
  DEBUG: 'var(--color-debug)'
};
const DEFAULT_LEVEL_COLOR = '#94a3b8';

interface LevelBar {
  level: string;
  count: number;
  pct: number;
  color: string;
}

interface ServiceBar {
  service_name: string;
  count: number;
  error_count: number;
  pct: number;
}

interface TimeSeriesBar {
  label: string;
  count: number;
  errorHeightPct: number;
  totalHeightPct: number;
}

@Component({
  selector: 'app-log-viewer',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatIconModule,
    MatButtonModule,
    MatSelectModule,
    MatInputModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './log-viewer.html',
  styleUrls: ['./log-viewer.css']
})
export class LogViewerComponent implements OnInit {
  logs: LogResponse[] = [];
  services: string[] = [];
  instances: string[] = [];

  // Filters
  selectedService = '';
  selectedInstance = '';
  selectedLevel = '';
  startDate = '';
  endDate = '';
  searchQuery = '';

  // Pagination
  currentPage = 0;
  pageSize = 20;
  hasMore = true;
  loading = false;

  // Interactive UX
  expandedLogId: number | null = null;
  rcaData: { [key: number]: LogAnalysisResponse | null } = {};
  rcaLoading: { [key: number]: boolean } = {};
  rcaError: { [key: number]: string } = {};

  // RCA -> Codebase diagnostics / Ask AI
  diagnosis: { [key: number]: DiagnoseCodebaseResponse | null } = {};
  diagnosing: { [key: number]: boolean } = {};
  diagnosisError: { [key: number]: string } = {};
  aiSuggestion: { [key: number]: AskAiResponse | null } = {};
  askingAi: { [key: number]: boolean } = {};
  aiError: { [key: number]: string } = {};

  // Summary / chart panel
  summary: LogSummaryResponse | null = null;
  summaryLoading = false;
  levelBars: LevelBar[] = [];
  serviceBars: ServiceBar[] = [];
  timeSeriesBars: TimeSeriesBar[] = [];
  rcaCoveragePct = 0;

  // Export
  exporting = false;

  message = '';
  messageType: 'success' | 'danger' | '' = '';

  constructor(private apiService: ApiService) {}

  ngOnInit() {
    this.loadServices();
    this.loadLogs();
    this.loadSummary();
  }

  private get activeFilters(): LogQueryFilters {
    return {
      service_name: this.selectedService || undefined,
      instance_id: this.selectedInstance || undefined,
      log_level: this.selectedLevel || undefined,
      start_date: this.startDate ? new Date(this.startDate).toISOString() : undefined,
      end_date: this.endDate ? new Date(this.endDate).toISOString() : undefined,
      search_query: this.searchQuery || undefined
    };
  }

  loadServices() {
    this.apiService.getLogSources().subscribe({
      next: (sources: LogFileResponse[]) => {
        // Extract unique service names
        const unique = new Set(sources.map(s => s.service_name));
        this.services = Array.from(unique).sort();

        // Extract unique instance ids (skip files with no instance dimension)
        const uniqueInstances = new Set(
          sources.map(s => s.instance_id).filter((i): i is string => !!i)
        );
        this.instances = Array.from(uniqueInstances).sort();
      },
      error: (err) => console.error('Error fetching services list', err)
    });
  }

  loadLogs(append = false) {
    this.loading = true;

    this.apiService.getLogs({
      ...this.activeFilters,
      skip: this.currentPage * this.pageSize,
      limit: this.pageSize
    }).subscribe({
      next: (data) => {
        if (append) {
          this.logs = [...this.logs, ...data];
        } else {
          this.logs = data;
        }

        // If we fetched fewer items than page size, we reached the end
        this.hasMore = data.length === this.pageSize;
        this.loading = false;
      },
      error: (err) => {
        console.error('Error loading logs', err);
        this.loading = false;
      }
    });
  }

  loadSummary() {
    this.summaryLoading = true;
    this.apiService.getLogsSummary(this.activeFilters).subscribe({
      next: (data) => {
        this.summary = data;
        this.buildChartData(data);
        this.summaryLoading = false;
      },
      error: (err) => {
        console.error('Error loading log summary', err);
        this.summaryLoading = false;
      }
    });
  }

  private buildChartData(summary: LogSummaryResponse) {
    const totalForLevels = Object.values(summary.level_counts).reduce((sum, n) => sum + n, 0) || 1;
    this.levelBars = Object.entries(summary.level_counts)
      .sort((a, b) => b[1] - a[1])
      .map(([level, count]) => ({
        level,
        count,
        pct: (count / totalForLevels) * 100,
        color: LEVEL_COLORS[level] || DEFAULT_LEVEL_COLOR
      }));

    const maxServiceCount = Math.max(1, ...summary.top_services.map(s => s.count));
    this.serviceBars = summary.top_services.map(s => ({
      ...s,
      pct: (s.count / maxServiceCount) * 100
    }));

    const maxBucketCount = Math.max(1, ...summary.time_series.map(p => p.count));
    this.timeSeriesBars = summary.time_series.map(p => ({
      label: this.formatBucketLabel(p.bucket, summary.bucket_granularity),
      count: p.count,
      totalHeightPct: (p.count / maxBucketCount) * 100,
      errorHeightPct: (p.error_count / maxBucketCount) * 100
    }));

    this.rcaCoveragePct = summary.errors_total > 0
      ? (summary.errors_with_rca / summary.errors_total) * 100
      : 0;
  }

  private formatBucketLabel(bucket: string, granularity: 'hour' | 'day'): string {
    const d = new Date(bucket);
    if (granularity === 'hour') {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  applyFilters() {
    this.currentPage = 0;
    this.loadLogs();
    this.loadSummary();
  }

  resetFilters() {
    this.selectedService = '';
    this.selectedInstance = '';
    this.selectedLevel = '';
    this.startDate = '';
    this.endDate = '';
    this.searchQuery = '';
    this.currentPage = 0;
    this.loadLogs();
    this.loadSummary();
  }

  setTodayFilter() {
    const now = new Date();
    const pad = (n: number) => n.toString().padStart(2, '0');
    const datePart = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    this.startDate = `${datePart}T00:00`;
    this.endDate = `${datePart}T23:59`;
    this.applyFilters();
  }

  nextPage() {
    if (this.hasMore && !this.loading) {
      this.currentPage++;
      this.loadLogs();
    }
  }

  prevPage() {
    if (this.currentPage > 0 && !this.loading) {
      this.currentPage--;
      this.loadLogs();
    }
  }

  downloadExport() {
    this.exporting = true;
    this.apiService.exportLogs(this.activeFilters).subscribe({
      next: (response) => {
        this.exporting = false;
        const blob = response.body;
        if (!blob) {
          this.showMessage('Export failed: empty response.', 'danger');
          return;
        }

        const totalMatched = Number(response.headers.get('X-Total-Matched') || '0');
        const rowsExported = Number(response.headers.get('X-Rows-Exported') || '0');

        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `logs_export_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.xlsx`;
        a.click();
        window.URL.revokeObjectURL(url);

        if (totalMatched > rowsExported) {
          this.showMessage(
            `Exported the first ${rowsExported.toLocaleString()} of ${totalMatched.toLocaleString()} matching rows (errors highlighted: green = RCA solution found, red = not yet solved). Narrow your filters to export the rest.`,
            'success'
          );
        } else {
          this.showMessage(`Exported ${rowsExported.toLocaleString()} rows. Errors are highlighted green (RCA solution found) or red (not yet solved).`, 'success');
        }
      },
      error: (err) => {
        this.exporting = false;
        console.error('Error exporting logs', err);
        this.showMessage('Failed to export logs.', 'danger');
      }
    });
  }

  showMessage(msg: string, type: 'success' | 'danger') {
    this.message = msg;
    this.messageType = type;
    setTimeout(() => {
      if (this.message === msg) {
        this.message = '';
        this.messageType = '';
      }
    }, 6000);
  }

  toggleExpand(logId: number) {
    if (this.expandedLogId === logId) {
      this.expandedLogId = null;
    } else {
      this.expandedLogId = logId;
      // Load RCA if not loaded
      if (!this.rcaData[logId] && !this.rcaLoading[logId]) {
        this.fetchExistingRca(logId);
      }
    }
  }

  fetchExistingRca(logId: number) {
    this.rcaLoading[logId] = true;
    this.apiService.getRcaAnalysis(logId).subscribe({
      next: (data) => {
        this.rcaData[logId] = data;
        this.rcaLoading[logId] = false;
        this.rcaError[logId] = '';
      },
      error: (err) => {
        // 404 is fine, just means no analysis yet
        this.rcaData[logId] = null;
        this.rcaLoading[logId] = false;
        if (err.status !== 404) {
          this.rcaError[logId] = 'Failed to load existing analysis.';
        }
      }
    });
  }

  triggerAnalysis(logId: number, forceNew = false) {
    this.rcaLoading[logId] = true;
    this.rcaError[logId] = '';
    this.apiService.triggerRcaAnalysis(logId, forceNew).subscribe({
      next: (data) => {
        this.rcaData[logId] = data;
        this.rcaLoading[logId] = false;
      },
      error: (err) => {
        console.error('Failed to trigger RCA:', err);
        this.rcaLoading[logId] = false;
        this.rcaError[logId] = err.error?.detail || 'Analysis failed. Check the configured AI provider in Settings.';
      }
    });
  }

  regenerateAnalysis(logId: number) {
    this.triggerAnalysis(logId, true);
  }

  diagnoseCodebase(logId: number) {
    this.diagnosing[logId] = true;
    this.diagnosisError[logId] = '';
    this.apiService.diagnoseCodebase(logId).subscribe({
      next: (data) => {
        this.diagnosis[logId] = data;
        this.diagnosing[logId] = false;
      },
      error: (err) => {
        this.diagnosing[logId] = false;
        this.diagnosisError[logId] = err.error?.detail || 'Failed to diagnose codebase.';
      }
    });
  }

  askAi(logId: number) {
    this.askingAi[logId] = true;
    this.aiError[logId] = '';
    const candidatePaths = this.diagnosis[logId]?.candidates.map(c => c.file_path);
    this.apiService.askAiForFix(logId, candidatePaths).subscribe({
      next: (data) => {
        this.aiSuggestion[logId] = data;
        this.askingAi[logId] = false;
      },
      error: (err) => {
        this.askingAi[logId] = false;
        this.aiError[logId] = err.error?.detail || 'Failed to get a suggestion from the AI provider.';
      }
    });
  }
}
