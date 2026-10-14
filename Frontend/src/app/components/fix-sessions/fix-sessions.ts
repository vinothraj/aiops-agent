import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService, FixSession, FIX_SESSION_TERMINAL } from '../../services/api.service';
import { FixSessionPanelComponent, FIX_STATUS_CLASS, FIX_STATUS_LABELS } from '../fix-session-panel/fix-session-panel';

const REFRESH_MS = 15000;

/** Tracks every Claude fix session -- manual ("Debug with Claude") and Auto-Fix queued. */
@Component({
  selector: 'app-fix-sessions',
  standalone: true,
  imports: [CommonModule, RouterModule, MatIconModule, MatButtonModule, MatProgressSpinnerModule, FixSessionPanelComponent],
  templateUrl: './fix-sessions.html',
  styleUrls: ['./fix-sessions.css']
})
export class FixSessionsComponent implements OnInit, OnDestroy {
  sessions: FixSession[] = [];
  loading = true;
  error = '';
  filter: 'all' | 'active' | 'completed' | 'failed' = 'active';
  expandedId: number | null = null;

  readonly labels = FIX_STATUS_LABELS;
  readonly statusClass = FIX_STATUS_CLASS;
  private refreshHandle: ReturnType<typeof setInterval> | null = null;

  constructor(private apiService: ApiService) {}

  ngOnInit() {
    this.load();
    this.refreshHandle = setInterval(() => this.load(true), REFRESH_MS);
  }

  ngOnDestroy() {
    if (this.refreshHandle) clearInterval(this.refreshHandle);
  }

  load(silent = false) {
    if (!silent) this.loading = true;
    this.apiService.getFixSessions().subscribe({
      next: (data) => { this.sessions = data; this.loading = false; this.error = ''; },
      error: (err) => { this.loading = false; this.error = err.error?.detail || 'Failed to load fix sessions.'; }
    });
  }

  setFilter(f: 'all' | 'active' | 'completed' | 'failed') {
    this.filter = f;
    this.expandedId = null;
  }

  get filtered(): FixSession[] {
    switch (this.filter) {
      case 'active': return this.sessions.filter(s => !FIX_SESSION_TERMINAL.includes(s.status));
      case 'completed': return this.sessions.filter(s => s.status === 'completed' || s.status === 'no_code_change');
      case 'failed': return this.sessions.filter(s => s.status === 'failed' || s.status === 'cancelled');
      default: return this.sessions;
    }
  }

  count(f: 'active' | 'completed' | 'failed' | 'queued'): number {
    switch (f) {
      case 'queued': return this.sessions.filter(s => s.status === 'queued').length;
      case 'active': return this.sessions.filter(s => !FIX_SESSION_TERMINAL.includes(s.status)).length;
      case 'completed': return this.sessions.filter(s => s.status === 'completed' || s.status === 'no_code_change').length;
      case 'failed': return this.sessions.filter(s => s.status === 'failed' || s.status === 'cancelled').length;
    }
  }

  toggle(id: number) {
    this.expandedId = this.expandedId === id ? null : id;
  }
}
