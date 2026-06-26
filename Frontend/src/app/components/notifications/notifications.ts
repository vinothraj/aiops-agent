import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatButtonModule } from '@angular/material/button';
import { ApiService, NotificationResponse, NotificationRecipient } from '../../services/api.service';

@Component({
  selector: 'app-notifications',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule, MatProgressSpinnerModule, MatButtonModule],
  templateUrl: './notifications.html',
  styleUrls: ['./notifications.css']
})
export class NotificationsComponent implements OnInit {
  activeTab: 'preferences' | 'history' | 'digests' = 'preferences';
  
  // Preferences Tab Data
  recipients: NotificationRecipient[] = [];
  loadingRecipients = false;
  editingRecipientId: number | null = null;
  
  // Recipient Form State
  recipientName = '';
  category = 'DEFAULT';
  channel = 'email';
  destination = '';
  isActive = true;
  
  // History Tab Data
  history: NotificationResponse[] = [];
  loadingHistory = false;
  
  // Digests Tab Data
  dailyDigest = '';
  weeklyInsights = '';
  loadingDigest = false;
  loadingInsights = false;

  // General Alerts
  successMessage: string | null = null;
  errorMessage: string | null = null;

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.loadRecipients();
  }

  switchTab(tab: 'preferences' | 'history' | 'digests'): void {
    this.activeTab = tab;
    this.successMessage = null;
    this.errorMessage = null;

    if (tab === 'preferences') {
      this.loadRecipients();
    } else if (tab === 'history') {
      this.loadHistory();
    }
  }

  // ─── Preferences Tab Actions ────────────────────────────────────────────────
  loadRecipients(): void {
    this.loadingRecipients = true;
    this.apiService.getNotificationRecipientList().subscribe({
      next: (data) => {
        this.recipients = data;
        this.loadingRecipients = false;
      },
      error: (err) => {
        console.error('Failed to load recipients:', err);
        this.errorMessage = 'Failed to load recipient routing configuration.';
        this.loadingRecipients = false;
      }
    });
  }

  saveRecipient(): void {
    if (!this.recipientName || !this.destination) {
      this.errorMessage = 'Please populate Name and Destination.';
      return;
    }

    const payload = {
      recipient_name: this.recipientName,
      category: this.category.toUpperCase(),
      channel: this.channel.toLowerCase(),
      destination: this.destination,
      is_active: this.isActive
    };

    const request = this.editingRecipientId 
      ? this.apiService.updateNotificationRecipient(this.editingRecipientId, payload)
      : this.apiService.createNotificationRecipient(payload);

    this.errorMessage = null;
    this.successMessage = null;

    request.subscribe({
      next: (res) => {
        this.successMessage = this.editingRecipientId ? 'Routing rule updated.' : 'Routing rule created.';
        this.clearForm();
        this.loadRecipients();
      },
      error: (err) => {
        console.error('Failed to save recipient:', err);
        this.errorMessage = 'Failed to save recipient configuration.';
      }
    });
  }

  startEdit(recipient: NotificationRecipient): void {
    this.editingRecipientId = recipient.id;
    this.recipientName = recipient.recipient_name;
    this.category = recipient.category;
    this.channel = recipient.channel;
    this.destination = recipient.destination;
    this.isActive = recipient.is_active;
  }

  cancelEdit(): void {
    this.clearForm();
  }

  deleteRecipient(id: number): void {
    if (!confirm('Are you sure you want to delete this routing rule?')) return;
    
    this.apiService.deleteNotificationRecipient(id).subscribe({
      next: () => {
        this.successMessage = 'Routing rule deleted successfully.';
        this.loadRecipients();
      },
      error: (err) => {
        console.error('Failed to delete recipient:', err);
        this.errorMessage = 'Failed to delete recipient routing rule.';
      }
    });
  }

  testRecipient(recipient: NotificationRecipient): void {
    this.successMessage = null;
    this.errorMessage = null;
    this.apiService.testNotification({ channel: recipient.channel, destination: recipient.destination }).subscribe({
      next: (res) => {
        if (res.status === 'success') {
          this.successMessage = `Verification test notification sent successfully to ${recipient.destination}!`;
        } else {
          this.errorMessage = `Test failed. Check recipient settings.`;
        }
      },
      error: (err) => {
        console.error('Test failed:', err);
        this.errorMessage = `Failed to trigger test notification.`;
      }
    });
  }

  clearForm(): void {
    this.editingRecipientId = null;
    this.recipientName = '';
    this.category = 'DEFAULT';
    this.channel = 'email';
    this.destination = '';
    this.isActive = true;
  }

  // ─── History Tab Actions ────────────────────────────────────────────────────
  loadHistory(): void {
    this.loadingHistory = true;
    this.apiService.getNotifications().subscribe({
      next: (data) => {
        this.history = data;
        this.loadingHistory = false;
      },
      error: (err) => {
        console.error('Failed to load history:', err);
        this.errorMessage = 'Could not load notification history.';
        this.loadingHistory = false;
      }
    });
  }

  retryAlert(id: number): void {
    this.successMessage = null;
    this.errorMessage = null;
    this.apiService.retryNotification(id).subscribe({
      next: (res) => {
        if (res.status === 'SENT') {
          this.successMessage = `Alert manually retried and delivered successfully!`;
        } else {
          this.errorMessage = `Retry failed: ${res.error_message || 'Unknown error'}`;
        }
        this.loadHistory();
      },
      error: (err) => {
        console.error('Retry failed:', err);
        this.errorMessage = 'Error dispatching retry request.';
      }
    });
  }

  // ─── Digest Tab Actions ─────────────────────────────────────────────────────
  generateDailyDigest(): void {
    this.loadingDigest = true;
    this.dailyDigest = '';
    this.apiService.getDailyDigest().subscribe({
      next: (res) => {
        this.dailyDigest = res.digest;
        this.loadingDigest = false;
      },
      error: (err) => {
        console.error('Digest generation failed:', err);
        this.dailyDigest = 'Failed to generate operational daily digest.';
        this.loadingDigest = false;
      }
    });
  }

  generateWeeklyInsights(): void {
    this.loadingInsights = true;
    this.weeklyInsights = '';
    this.apiService.getWeeklyInsights().subscribe({
      next: (res) => {
        this.weeklyInsights = res.insights;
        this.loadingInsights = false;
      },
      error: (err) => {
        console.error('Insights generation failed:', err);
        this.weeklyInsights = 'Failed to generate weekly SRE reliability report.';
        this.loadingInsights = false;
      }
    });
  }
}
