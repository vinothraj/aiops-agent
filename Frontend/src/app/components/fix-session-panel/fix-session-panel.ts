import { Component, Input, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService, FixSession, FixSessionStatus, FIX_SESSION_TERMINAL } from '../../services/api.service';

/** Happy-path milestones shown as the progress stepper. */
const STEPS: { status: FixSessionStatus; label: string }[] = [
  { status: 'queued', label: 'Queued' },
  { status: 'in_progress', label: 'Investigating' },
  { status: 'fix_ready', label: 'Fix ready' },
  { status: 'pushed', label: 'Pushed / MR' },
  { status: 'completed', label: 'Completed' },
];

export const FIX_STATUS_LABELS: Record<FixSessionStatus, string> = {
  queued: 'Queued',
  in_progress: 'Investigating',
  fix_ready: 'Fix ready',
  pushed: 'Pushed',
  completed: 'Completed',
  no_code_change: 'No code change',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export const FIX_STATUS_CLASS: Record<FixSessionStatus, string> = {
  queued: 'bg-secondary text-light',
  in_progress: 'bg-info text-info',
  fix_ready: 'bg-primary text-primary',
  pushed: 'bg-primary text-primary',
  completed: 'bg-success text-success',
  no_code_change: 'bg-secondary text-light',
  failed: 'bg-danger text-danger',
  cancelled: 'bg-secondary text-secondary',
};

const POLL_MS = 5000;

/**
 * "Debug with Claude": opens a tracked fix session for a log, hands the
 * Claude Code brief to the user (copy / download), and live-tracks the
 * progress Claude reports back. Used in the Log Explorer (by logId) and on
 * the Fix Sessions page (by an existing session).
 */
@Component({
  selector: 'app-fix-session-panel',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatButtonModule, MatProgressSpinnerModule],
  templateUrl: './fix-session-panel.html',
  styleUrls: ['./fix-session-panel.css']
})
export class FixSessionPanelComponent implements OnInit, OnDestroy {
  /** Start/resume a session for this log (Log Explorer). */
  @Input() logId?: number;
  /** Optional "Ask AI" suggestion handed to Claude as a starting hypothesis. */
  @Input() aiHypothesis?: string;
  /** Show an existing session (Fix Sessions page). */
  @Input() session?: FixSession;

  brief: string | null = null;
  showBrief = false;
  loading = false;
  error = '';
  copied = false;

  readonly steps = STEPS;
  readonly labels = FIX_STATUS_LABELS;
  readonly statusClass = FIX_STATUS_CLASS;
  private pollHandle: ReturnType<typeof setInterval> | null = null;

  constructor(private apiService: ApiService) {}

  ngOnInit() {
    if (this.session) {
      // List rows arrive without events -- load the full record.
      this.refresh();
      this.startPolling();
    } else if (this.logId != null) {
      // Resume tracking an open session for this log, if there is one.
      this.apiService.getFixSessions('active', this.logId).subscribe({
        next: (sessions) => {
          if (sessions.length) {
            this.session = sessions[0];
            this.refresh();
            this.startPolling();
          }
        }
      });
    }
  }

  ngOnDestroy() {
    this.stopPolling();
  }

  get isTerminal(): boolean {
    return !!this.session && FIX_SESSION_TERMINAL.includes(this.session.status);
  }

  /** Index of the current status in the stepper (-1 for off-path terminal states). */
  get stepIndex(): number {
    if (!this.session) return -1;
    return STEPS.findIndex(s => s.status === this.session!.status);
  }

  /** Creates the session (or re-issues the brief for an open one). Rotates the callback token. */
  start() {
    this.loading = true;
    this.error = '';
    const request = this.session && !this.isTerminal
      ? this.apiService.reissueFixBrief(this.session.id)
      : this.apiService.createFixSession(this.logId ?? this.session!.log_id, this.aiHypothesis);
    request.subscribe({
      next: (res) => {
        this.session = res.session;
        this.brief = res.brief;
        this.showBrief = false;
        this.loading = false;
        this.startPolling();
      },
      error: (err) => {
        this.loading = false;
        this.error = err.error?.detail || 'Could not create the fix session.';
      }
    });
  }

  copyBrief() {
    if (!this.brief) return;
    navigator.clipboard.writeText(this.brief).then(
      () => { this.copied = true; setTimeout(() => this.copied = false, 2500); },
      () => this.error = 'Could not copy to clipboard -- use Download instead.'
    );
  }

  downloadBrief() {
    if (!this.brief || !this.session) return;
    const blob = new Blob([this.brief], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aiops-fix-session-${this.session.id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  cancel() {
    if (!this.session || !confirm(`Cancel fix session #${this.session.id}? Claude will no longer be able to report on it.`)) return;
    this.apiService.cancelFixSession(this.session.id).subscribe({
      next: (s) => { this.session = s; this.brief = null; this.stopPolling(); },
      error: (err) => this.error = err.error?.detail || 'Could not cancel the session.'
    });
  }

  private refresh() {
    if (!this.session) return;
    this.apiService.getFixSession(this.session.id).subscribe({
      next: (s) => {
        this.session = s;
        if (this.isTerminal) this.stopPolling();
      }
    });
  }

  private startPolling() {
    this.stopPolling();
    if (this.isTerminal) return;
    this.pollHandle = setInterval(() => this.refresh(), POLL_MS);
  }

  private stopPolling() {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
  }
}
