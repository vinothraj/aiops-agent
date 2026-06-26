import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService, IncidentDecisionResponse, TimelineEventResponse } from '../../services/api.service';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

@Component({
  selector: 'app-incident-queue',
  standalone: true,
  imports: [
    CommonModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './incident-queue.html',
  styleUrls: ['./incident-queue.css']
})
export class IncidentQueueComponent implements OnInit {
  incidents: IncidentDecisionResponse[] = [];
  loading = true;
  error = '';
  expandedId: number | null = null;
  activeFilter: string = 'ALL';

  // Timelines storage
  timelines: { [incidentId: number]: TimelineEventResponse[] } = {};
  loadingTimelines: { [incidentId: number]: boolean } = {};

  // Summary counters
  totalOpen = 0;
  p1Count = 0;
  p2Count = 0;
  p3Count = 0;
  p4Count = 0;

  constructor(private apiService: ApiService) {}

  ngOnInit() {
    this.loadIncidents();
  }

  loadIncidents(priority?: string) {
    this.loading = true;
    this.error = '';
    this.activeFilter = priority || 'ALL';

    const filters: any = { limit: 100 };
    if (priority) filters.priority = priority;

    this.apiService.getIncidents(filters).subscribe({
      next: (data) => {
        this.incidents = data;
        this.loading = false;
        this.computeSummary();
      },
      error: (err) => {
        console.error('Failed to load incidents:', err);
        this.error = 'Could not load incident queue.';
        this.loading = false;
      }
    });
  }

  computeSummary() {
    this.totalOpen = this.incidents.filter(i => i.status === 'OPEN').length;
    this.p1Count = this.incidents.filter(i => i.priority === 'P1').length;
    this.p2Count = this.incidents.filter(i => i.priority === 'P2').length;
    this.p3Count = this.incidents.filter(i => i.priority === 'P3').length;
    this.p4Count = this.incidents.filter(i => i.priority === 'P4').length;
  }

  toggleExpanded(id: number) {
    this.expandedId = this.expandedId === id ? null : id;
    if (this.expandedId === id && !this.timelines[id]) {
      this.loadTimeline(id);
    }
  }

  loadTimeline(id: number) {
    this.loadingTimelines[id] = true;
    this.apiService.getIncidentTimeline(id).subscribe({
      next: (events) => {
        this.timelines[id] = events;
        this.loadingTimelines[id] = false;
      },
      error: (err) => {
        console.error(`Failed to load timeline for incident ${id}:`, err);
        this.loadingTimelines[id] = false;
      }
    });
  }

  getPriorityClass(priority: string): string {
    switch (priority) {
      case 'P1': return 'priority-p1';
      case 'P2': return 'priority-p2';
      case 'P3': return 'priority-p3';
      case 'P4': return 'priority-p4';
      default: return 'priority-p4';
    }
  }

  getActionClass(action: string): string {
    switch (action) {
      case 'IMMEDIATE_ESCALATION': return 'action-escalate';
      case 'CREATE_INCIDENT': return 'action-create';
      case 'INVESTIGATE': return 'action-investigate';
      case 'MONITOR': return 'action-monitor';
      case 'IGNORE': return 'action-ignore';
      default: return 'action-monitor';
    }
  }

  getActionIcon(action: string): string {
    switch (action) {
      case 'IMMEDIATE_ESCALATION': return 'emergency';
      case 'CREATE_INCIDENT': return 'bug_report';
      case 'INVESTIGATE': return 'search';
      case 'MONITOR': return 'visibility';
      case 'IGNORE': return 'check_circle';
      default: return 'info';
    }
  }

  formatAction(action: string): string {
    return action.replace(/_/g, ' ');
  }

  getParsedServices(affectedServices: string | undefined): string[] {
    if (!affectedServices) return [];
    try {
      return JSON.parse(affectedServices);
    } catch (e) {
      return [affectedServices];
    }
  }
}

