import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService, LogAnalysisResponse } from '../../services/api.service';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-rca-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    RouterLink
  ],
  templateUrl: './rca-dashboard.html',
  styleUrls: ['./rca-dashboard.css']
})
export class RcaDashboardComponent implements OnInit {
  analyses: LogAnalysisResponse[] = [];
  loading = true;
  error = '';

  constructor(private apiService: ApiService) {}

  ngOnInit() {
    this.loadAnalyses();
  }

  loadAnalyses() {
    this.loading = true;
    this.error = '';
    this.apiService.getAllRcaAnalyses(0, 50).subscribe({
      next: (data) => {
        this.analyses = data;
        this.loading = false;
      },
      error: (err) => {
        console.error('Failed to load analyses:', err);
        this.error = 'Could not load RCA history.';
        this.loading = false;
      }
    });
  }
}
