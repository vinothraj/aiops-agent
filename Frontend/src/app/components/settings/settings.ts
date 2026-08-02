import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, AiProviderSettingsResponse } from '../../services/api.service';
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

  // Target codebase path (used by RCA's Diagnose in Codebase / Ask AI)
  codebasePath = '';
  codebasePathSaved = '';
  codebasePathLoading = false;
  codebasePathSaving = false;

  // AI provider (Claude / Gemini / local Ollama) used by RCA's "Ask AI"
  aiProvider: AiProviderSettingsResponse | null = null;
  selectedProvider: 'claude' | 'gemini' | 'ollama' = 'claude';
  ollamaBaseUrl = '';
  ollamaModel = '';
  aiProviderLoading = false;
  aiProviderSaving = false;
  autoRcaEnabled = false;
  // Write-only inputs: never populated from the server response (the API
  // never echoes a stored key back), cleared again after every save.
  claudeApiKeyInput = '';
  geminiApiKeyInput = '';

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
    this.loadAiProvider();
  }

  loadAiProvider() {
    this.aiProviderLoading = true;
    this.apiService.getAiProviderSettings().subscribe({
      next: (data) => {
        this.aiProvider = data;
        this.selectedProvider = data.provider;
        this.ollamaBaseUrl = data.ollama_base_url;
        this.ollamaModel = data.ollama_model;
        this.autoRcaEnabled = data.auto_rca_enabled;
        this.aiProviderLoading = false;
      },
      error: (err) => {
        console.error('Error fetching AI provider settings', err);
        this.aiProviderLoading = false;
      }
    });
  }

  saveAiProvider() {
    this.aiProviderSaving = true;
    const payload: {
      provider: string; ollama_base_url?: string; ollama_model?: string; auto_rca_enabled?: boolean;
      claude_api_key?: string; gemini_api_key?: string;
    } = {
      provider: this.selectedProvider,
      auto_rca_enabled: this.autoRcaEnabled
    };
    // Only include Ollama fields when non-empty -- omitting them (rather than
    // sending '') leaves the stored value untouched, so saving while on the
    // Claude/Gemini tab (or before the Ollama fields have loaded) can't
    // accidentally blank out the configured Ollama base URL/model.
    if (this.ollamaBaseUrl.trim()) payload.ollama_base_url = this.ollamaBaseUrl.trim();
    if (this.ollamaModel.trim()) payload.ollama_model = this.ollamaModel.trim();
    // Only include a key if the user actually typed one -- omitting it
    // leaves whatever's already stored untouched (see clearApiKey() to
    // explicitly remove one instead).
    if (this.claudeApiKeyInput.trim()) payload.claude_api_key = this.claudeApiKeyInput.trim();
    if (this.geminiApiKeyInput.trim()) payload.gemini_api_key = this.geminiApiKeyInput.trim();

    this.apiService.setAiProviderSettings(payload).subscribe({
      next: (data) => {
        this.aiProvider = data;
        this.aiProviderSaving = false;
        this.claudeApiKeyInput = '';
        this.geminiApiKeyInput = '';
        this.showMessage(`AI provider set to ${data.provider}.`, 'success');
      },
      error: (err) => {
        this.aiProviderSaving = false;
        this.showMessage(`Failed to save AI provider: ${err.error?.detail || err.message}`, 'danger');
      }
    });
  }

  clearApiKey(provider: 'claude' | 'gemini') {
    this.aiProviderSaving = true;
    const payload: any = {
      provider: this.selectedProvider,
      auto_rca_enabled: this.autoRcaEnabled
    };
    if (this.ollamaBaseUrl.trim()) payload.ollama_base_url = this.ollamaBaseUrl.trim();
    if (this.ollamaModel.trim()) payload.ollama_model = this.ollamaModel.trim();
    payload[provider === 'claude' ? 'claude_api_key' : 'gemini_api_key'] = '';

    this.apiService.setAiProviderSettings(payload).subscribe({
      next: (data) => {
        this.aiProvider = data;
        this.aiProviderSaving = false;
        this.showMessage(`Cleared stored ${provider} API key (falls back to .env if set there).`, 'success');
      },
      error: (err) => {
        this.aiProviderSaving = false;
        this.showMessage(`Failed to clear key: ${err.error?.detail || err.message}`, 'danger');
      }
    });
  }

  onToggleAutoRca(event: Event) {
    const checkbox = event.target as HTMLInputElement;
    const wantsEnabled = checkbox.checked;

    if (wantsEnabled) {
      const confirmed = window.confirm(
        'Enabling automatic root cause analysis will analyze every new ERROR log automatically as it arrives -- no button click needed.\n\n' +
        'This only actually runs while AI Provider is set to "Local Llama via Ollama" (free, no tokens). ' +
        'If you switch to Claude or Gemini, auto-analysis stays paused even with this enabled, since those cost real API tokens per call.\n\n' +
        'Enable automatic analysis?'
      );
      if (!confirmed) {
        checkbox.checked = false;
        return;
      }
    }

    this.autoRcaEnabled = wantsEnabled;
    this.saveAiProvider();
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
