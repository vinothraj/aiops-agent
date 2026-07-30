import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  ApiService,
  IncidentGroupResponse,
  IncidentGroupDetailResponse
} from '../../services/api.service';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

@Component({
  selector: 'app-incident-groups',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatProgressSpinnerModule],
  templateUrl: './incident-groups.html',
  styleUrls: ['./incident-groups.css']
})
export class IncidentGroupsComponent implements OnInit {
  groups: IncidentGroupResponse[] = [];
  loading = true;
  error = '';

  expandedId: number | null = null;
  details: { [groupId: number]: IncidentGroupDetailResponse } = {};
  loadingDetail: { [groupId: number]: boolean } = {};

  totalRecurrences = 0;
  tokensSaved = 0; // every occurrence beyond the first reused a solution instead of calling Gemini

  constructor(private apiService: ApiService) {}

  ngOnInit() {
    this.loadGroups();
  }

  loadGroups() {
    this.loading = true;
    this.error = '';
    this.apiService.getIncidentGroups(0, 100).subscribe({
      next: (data) => {
        this.groups = data;
        this.loading = false;
        this.computeSummary();
      },
      error: (err) => {
        console.error('Failed to load incident groups:', err);
        this.error = 'Could not load recurring-incident groups.';
        this.loading = false;
      }
    });
  }

  computeSummary() {
    this.totalRecurrences = this.groups.reduce((sum, g) => sum + g.occurrence_count, 0);
    this.tokensSaved = this.groups.reduce((sum, g) => sum + Math.max(g.occurrence_count - 1, 0), 0);
  }

  toggleExpanded(group: IncidentGroupResponse) {
    this.expandedId = this.expandedId === group.id ? null : group.id;
    if (this.expandedId === group.id && !this.details[group.id]) {
      this.loadDetail(group.id);
    }
  }

  loadDetail(groupId: number) {
    this.loadingDetail[groupId] = true;
    this.apiService.getIncidentGroupDetail(groupId).subscribe({
      next: (detail) => {
        this.details[groupId] = detail;
        this.loadingDetail[groupId] = false;
      },
      error: (err) => {
        console.error(`Failed to load incident group ${groupId}:`, err);
        this.loadingDetail[groupId] = false;
      }
    });
  }

  recurrenceClass(count: number): string {
    if (count >= 10) return 'recurrence-high';
    if (count >= 3) return 'recurrence-medium';
    return 'recurrence-low';
  }
}
