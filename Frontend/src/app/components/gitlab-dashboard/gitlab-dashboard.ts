import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService, GitlabIssueResponse } from '../../services/api.service';

@Component({
  selector: 'app-gitlab-dashboard',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatProgressSpinnerModule],
  templateUrl: './gitlab-dashboard.html',
  styleUrls: ['./gitlab-dashboard.css']
})
export class GitlabDashboardComponent implements OnInit {
  issues: GitlabIssueResponse[] = [];
  loading = false;
  syncing = false;
  error: string | null = null;
  expandedId: number | null = null;

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.loadIssues();
  }

  loadIssues(): void {
    this.loading = true;
    this.error = null;
    this.apiService.getGitlabIssues().subscribe({
      next: (data) => {
        this.issues = data;
        this.loading = false;
      },
      error: (err) => {
        console.error('Failed to load GitLab issues', err);
        this.error = 'Failed to load GitLab issues. Please check the backend connection.';
        this.loading = false;
      }
    });
  }

  syncIssues(): void {
    if (this.syncing) return;
    this.syncing = true;
    this.apiService.syncGitlabIssues().subscribe({
      next: (data) => {
        // Refresh the list after sync
        this.loadIssues();
        this.syncing = false;
      },
      error: (err) => {
        console.error('Failed to sync GitLab issues', err);
        this.error = 'Failed to sync with GitLab. Please check your token configuration.';
        this.syncing = false;
      }
    });
  }

  toggleExpanded(id: number): void {
    this.expandedId = this.expandedId === id ? null : id;
  }

  getParsedLabels(labelsStr: string | undefined): string[] {
    if (!labelsStr) return [];
    try {
      return JSON.parse(labelsStr);
    } catch (e) {
      return [];
    }
  }
}
