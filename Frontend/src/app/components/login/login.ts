import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule],
  templateUrl: './login.html',
  styleUrls: ['./login.css']
})
export class LoginComponent {
  mode: 'signin' | 'register' = 'signin';
  name = '';
  email = '';
  password = '';
  confirm = '';
  busy = false;
  error = '';
  info = '';

  constructor(private auth: AuthService, private router: Router) {
    if (auth.isLoggedIn) this.router.navigate(['/dashboard']);
  }

  setMode(mode: 'signin' | 'register') {
    this.mode = mode;
    this.error = '';
    this.info = '';
  }

  submit() {
    this.error = '';
    this.info = '';
    if (!this.email.trim() || !this.password) {
      this.error = 'Email and password are required.';
      return;
    }
    if (this.mode === 'register') {
      if (!this.name.trim()) { this.error = 'Name is required.'; return; }
      if (this.password.length < 8) { this.error = 'Password must be at least 8 characters.'; return; }
      if (this.password !== this.confirm) { this.error = 'Passwords do not match.'; return; }
    }
    this.busy = true;
    if (this.mode === 'signin') {
      this.auth.login(this.email, this.password).subscribe({
        next: () => { this.busy = false; this.router.navigate(['/dashboard']); },
        error: err => { this.busy = false; this.error = this.messageOf(err); }
      });
    } else {
      this.auth.register(this.name, this.email, this.password).subscribe({
        next: res => {
          this.busy = false;
          this.mode = 'signin';
          this.password = this.confirm = '';
          this.info = res.message;
        },
        error: err => { this.busy = false; this.error = this.messageOf(err); }
      });
    }
  }

  private messageOf(err: any): string {
    if (err.status === 0) return 'Cannot reach the server. Is the backend running?';
    const d = err.error?.detail;
    return typeof d === 'string' ? d : 'Something went wrong. Please try again.';
  }
}
