import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { ApiService, LogStatsSummary, LogResponse } from '../../services/api.service';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatCardModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './dashboard.html',
  styleUrls: ['./dashboard.css']
})
export class DashboardComponent implements OnInit, OnDestroy {
  stats: LogStatsSummary = {
    total_logs: 0,
    error_logs: 0,
    warning_logs: 0,
    services: 0
  };
  recentErrors: LogResponse[] = [];
  loading = true;
  refreshInterval: any;

  constructor(private apiService: ApiService) {}

  ngOnInit() {
    this.loadData();
    // Auto-refresh every 10 seconds
    this.refreshInterval = setInterval(() => {
      this.loadData(false);
    }, 10000);
  }

  ngOnDestroy() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  }

  loadData(showSpinner = true) {
    if (showSpinner) {
      this.loading = true;
    }
    
    // Fetch stats
    this.apiService.getStatsSummary().subscribe({
      next: (data) => {
        this.stats = data;
        if (showSpinner) this.loading = false;
      },
      error: (err) => {
        console.error('Error fetching dashboard stats', err);
        if (showSpinner) this.loading = false;
      }
    });

    // Fetch recent error logs
    this.apiService.getLogs({ log_level: 'ERROR', limit: 5 }).subscribe({
      next: (data) => {
        this.recentErrors = data;
      },
      error: (err) => {
        console.error('Error fetching recent errors', err);
      }
    });
  }

  // Calculate percentages for SVG chart
  getErrorPercentage(): number {
    if (!this.stats.total_logs) return 0;
    return (this.stats.error_logs / this.stats.total_logs) * 100;
  }

  getWarningPercentage(): number {
    if (!this.stats.total_logs) return 0;
    return (this.stats.warning_logs / this.stats.total_logs) * 100;
  }

  getNormalPercentage(): number {
    if (!this.stats.total_logs) return 0;
    const normal = this.stats.total_logs - this.stats.error_logs - this.stats.warning_logs;
    return (normal / this.stats.total_logs) * 100;
  }
}
