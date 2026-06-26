import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, LogResponse, LogFileResponse, LogAnalysisResponse } from '../../services/api.service';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

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
  
  // Filters
  selectedService = '';
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

  constructor(private apiService: ApiService) {}

  ngOnInit() {
    this.loadServices();
    this.loadLogs();
  }

  loadServices() {
    this.apiService.getLogSources().subscribe({
      next: (sources: LogFileResponse[]) => {
        // Extract unique service names
        const unique = new Set(sources.map(s => s.service_name));
        this.services = Array.from(unique).sort();
      },
      error: (err) => console.error('Error fetching services list', err)
    });
  }

  loadLogs(append = false) {
    this.loading = true;
    
    // Construct date string or null
    const startStr = this.startDate ? new Date(this.startDate).toISOString() : undefined;
    const endStr = this.endDate ? new Date(this.endDate).toISOString() : undefined;

    this.apiService.getLogs({
      service_name: this.selectedService || undefined,
      log_level: this.selectedLevel || undefined,
      start_date: startStr,
      end_date: endStr,
      search_query: this.searchQuery || undefined,
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

  applyFilters() {
    this.currentPage = 0;
    this.loadLogs();
  }

  resetFilters() {
    this.selectedService = '';
    this.selectedLevel = '';
    this.startDate = '';
    this.endDate = '';
    this.searchQuery = '';
    this.currentPage = 0;
    this.loadLogs();
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

  triggerAnalysis(logId: number) {
    this.rcaLoading[logId] = true;
    this.rcaError[logId] = '';
    this.apiService.triggerRcaAnalysis(logId).subscribe({
      next: (data) => {
        this.rcaData[logId] = data;
        this.rcaLoading[logId] = false;
      },
      error: (err) => {
        console.error('Failed to trigger RCA:', err);
        this.rcaLoading[logId] = false;
        this.rcaError[logId] = 'Analysis failed. Make sure Gemini API Key is configured and running properly.';
      }
    });
  }
}
