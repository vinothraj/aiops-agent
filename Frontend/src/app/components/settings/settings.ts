import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

const RESET_CONFIRMATION_PHRASE = 'RESET DATABASE';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './settings.html',
  styleUrls: ['./settings.css']
})
export class SettingsComponent implements OnInit {
  readonly confirmationPhrase = RESET_CONFIRMATION_PHRASE;

  stats: { [table: string]: number } = {};
  statsLoading = false;
  totalRows = 0;

  // Target codebase path (used by RCA's Diagnose in Codebase / Ask Claude)
  codebasePath = '';
  codebasePathSaved = '';
  codebasePathLoading = false;
  codebasePathSaving = false;

  // Two-step reset confirmation flow: 0 = idle, 1 = "are you sure", 2 = type-to-confirm
  confirmStep = 0;
  typedConfirmation = '';
  resetting = false;

  message = '';
  messageType: 'success' | 'danger' | '' = '';

  constructor(private apiService: ApiService) {}

  ngOnInit() {
    this.loadStats();
    this.loadCodebasePath();
  }

  loadCodebasePath() {
    this.codebasePathLoading = true;
    this.apiService.getCodebasePath().subscribe({
      next: (data) => {
        this.codebasePath = data.value || '';
        this.codebasePathSaved = data.value || '';
        this.codebasePathLoading = false;
      },
      error: (err) => {
        console.error('Error fetching codebase path', err);
        this.codebasePathLoading = false;
      }
    });
  }

  saveCodebasePath() {
    this.codebasePathSaving = true;
    this.apiService.setCodebasePath(this.codebasePath.trim()).subscribe({
      next: (data) => {
        this.codebasePathSaving = false;
        this.codebasePath = data.value || '';
        this.codebasePathSaved = data.value || '';
        this.showMessage(
          this.codebasePathSaved ? `Target codebase path saved: ${this.codebasePathSaved}` : 'Target codebase path cleared.',
          'success'
        );
      },
      error: (err) => {
        this.codebasePathSaving = false;
        this.showMessage(`Failed to save path: ${err.error?.detail || err.message}`, 'danger');
      }
    });
  }

  loadStats() {
    this.statsLoading = true;
    this.apiService.getDatabaseStats().subscribe({
      next: (data) => {
        this.stats = data;
        this.totalRows = Object.values(data).reduce((sum, n) => sum + n, 0);
        this.statsLoading = false;
      },
      error: (err) => {
        console.error('Error fetching database stats', err);
        this.statsLoading = false;
      }
    });
  }

  get statEntries(): { table: string; count: number }[] {
    return Object.entries(this.stats).map(([table, count]) => ({ table, count }));
  }

  startReset() {
    this.confirmStep = 1;
  }

  proceedToTypeConfirm() {
    this.confirmStep = 2;
    this.typedConfirmation = '';
  }

  cancelReset() {
    this.confirmStep = 0;
    this.typedConfirmation = '';
  }

  get typedConfirmationMatches(): boolean {
    return this.typedConfirmation === this.confirmationPhrase;
  }

  confirmReset() {
    if (!this.typedConfirmationMatches || this.resetting) {
      return;
    }

    this.resetting = true;
    this.apiService.resetDatabase(this.typedConfirmation).subscribe({
      next: (res) => {
        this.resetting = false;
        this.confirmStep = 0;
        this.typedConfirmation = '';
        this.showMessage(`Database reset complete. ${res.tables_cleared.length} tables cleared.`, 'success');
        this.loadStats();
      },
      error: (err) => {
        this.resetting = false;
        this.showMessage(`Reset failed: ${err.error?.detail || err.message}`, 'danger');
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
}
