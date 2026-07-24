import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, LogFileResponse, MonitoredSourceRootResponse } from '../../services/api.service';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

@Component({
  selector: 'app-log-sources',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './log-sources.html',
  styleUrls: ['./log-sources.css']
})
export class LogSourcesComponent implements OnInit {
  sources: LogFileResponse[] = [];
  loading = false;
  reprocessingIds: Set<number> = new Set();
  reprocessingAll = false;
  message = '';
  messageType: 'success' | 'danger' | '' = '';

  roots: MonitoredSourceRootResponse[] = [];
  rootsLoading = false;
  newRootPath = '';
  newRootLabel = '';
  addingRoot = false;
  removingRootIds: Set<number> = new Set();

  constructor(private apiService: ApiService) {}

  ngOnInit() {
    this.loadSources();
    this.loadRoots();
  }

  loadSources() {
    this.loading = true;
    this.apiService.getLogSources().subscribe({
      next: (data) => {
        this.sources = data;
        this.loading = false;
      },
      error: (err) => {
        console.error('Error fetching log sources', err);
        this.loading = false;
      }
    });
  }

  reprocessFile(source: LogFileResponse) {
    this.reprocessingIds.add(source.id);
    this.showMessage(`Reprocessing initiated for ${source.file_name}...`, 'success');
    
    this.apiService.reprocessLogs(source.id).subscribe({
      next: (res) => {
        this.reprocessingIds.delete(source.id);
        this.showMessage(`Reprocessing completed for ${source.file_name}`, 'success');
        this.loadSources();
      },
      error: (err) => {
        this.reprocessingIds.delete(source.id);
        this.showMessage(`Reprocessing failed for ${source.file_name}: ${err.message}`, 'danger');
        this.loadSources();
      }
    });
  }

  reprocessAll() {
    this.reprocessingAll = true;
    this.showMessage('Reprocessing initiated for all monitored files...', 'success');

    this.apiService.reprocessLogs().subscribe({
      next: (res) => {
        this.reprocessingAll = false;
        this.showMessage('Reprocessing completed for all files.', 'success');
        this.loadSources();
      },
      error: (err) => {
        this.reprocessingAll = false;
        this.showMessage(`Reprocessing failed: ${err.message}`, 'danger');
        this.loadSources();
      }
    });
  }

  loadRoots() {
    this.rootsLoading = true;
    this.apiService.getMonitoredRoots().subscribe({
      next: (data) => {
        this.roots = data;
        this.rootsLoading = false;
      },
      error: (err) => {
        console.error('Error fetching monitored roots', err);
        this.rootsLoading = false;
      }
    });
  }

  addRoot() {
    const path = this.newRootPath.trim();
    if (!path) {
      this.showMessage('Enter a path before adding it.', 'danger');
      return;
    }

    this.addingRoot = true;
    this.apiService.addMonitoredRoot(path, this.newRootLabel.trim() || undefined).subscribe({
      next: () => {
        this.addingRoot = false;
        this.newRootPath = '';
        this.newRootLabel = '';
        this.showMessage(`Now monitoring ${path}`, 'success');
        this.loadRoots();
      },
      error: (err) => {
        this.addingRoot = false;
        this.showMessage(`Failed to add source: ${err.error?.detail || err.message}`, 'danger');
      }
    });
  }

  removeRoot(root: MonitoredSourceRootResponse) {
    this.removingRootIds.add(root.id);
    this.apiService.deleteMonitoredRoot(root.id).subscribe({
      next: () => {
        this.removingRootIds.delete(root.id);
        this.showMessage(`Stopped monitoring ${root.path}`, 'success');
        this.loadRoots();
      },
      error: (err) => {
        this.removingRootIds.delete(root.id);
        this.showMessage(`Failed to remove source: ${err.error?.detail || err.message}`, 'danger');
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
    }, 5000);
  }
}
