import { Component, OnInit } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { AuthService, AuthUser } from '../../services/auth.service';

@Component({
  selector: 'app-user-management',
  standalone: true,
  imports: [CommonModule, MatIconModule, DatePipe],
  templateUrl: './user-management.html',
  styleUrls: ['./user-management.css']
})
export class UserManagementComponent implements OnInit {
  users: AuthUser[] = [];
  filter: '' | 'pending' | 'approved' | 'rejected' | 'disabled' = 'pending';
  filters: Array<'' | 'pending' | 'approved' | 'rejected' | 'disabled'> = ['pending', 'approved', 'rejected', 'disabled', ''];
  loading = false;
  error = '';
  pendingCount = 0;

  constructor(public auth: AuthService) {}

  ngOnInit() { this.load(); }

  load() {
    this.loading = true;
    this.error = '';
    this.auth.listUsers(this.filter || undefined).subscribe({
      next: u => { this.users = u; this.loading = false; this.refreshPending(); },
      error: e => { this.loading = false; this.error = e.error?.detail || 'Failed to load users.'; }
    });
  }

  private refreshPending() {
    this.auth.listUsers('pending').subscribe(p => this.pendingCount = p.length);
  }

  setFilter(f: typeof this.filter) { this.filter = f; this.load(); }

  act(u: AuthUser, action: 'approve' | 'reject' | 'disable') {
    this.auth.setUserStatus(u.id, action).subscribe({
      next: () => this.load(),
      error: e => this.error = e.error?.detail || 'Action failed.'
    });
  }

  toggleRole(u: AuthUser) {
    const role = u.role === 'admin' ? 'user' : 'admin';
    if (!confirm(`Make ${u.name} ${role === 'admin' ? 'an administrator' : 'a regular user'}?`)) return;
    this.auth.setUserRole(u.id, role).subscribe({
      next: () => this.load(),
      error: e => this.error = e.error?.detail || 'Action failed.'
    });
  }

  badge(status: string): string {
    return { pending: 'text-bg-warning', approved: 'text-bg-success', rejected: 'text-bg-danger', disabled: 'text-bg-secondary' }[status] || 'text-bg-light';
  }
}
