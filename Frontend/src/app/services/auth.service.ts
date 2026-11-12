import { Injectable, computed, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';

export interface AuthUser {
  id: number;
  email: string;
  name: string;
  role: 'user' | 'admin';
  status: 'pending' | 'approved' | 'rejected' | 'disabled';
  created_at: string;
  approved_by?: string;
  approved_at?: string;
  last_login_at?: string;
}

interface LoginResponse {
  access_token: string;
  user: AuthUser;
}

const TOKEN_KEY = 'aiops_token';
const USER_KEY = 'aiops_user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private baseUrl = 'http://localhost:8000/api';

  readonly user = signal<AuthUser | null>(this.loadUser());
  readonly isAdmin = computed(() => this.user()?.role === 'admin');

  constructor(private http: HttpClient, private router: Router) {}

  get token(): string | null {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  }

  get isLoggedIn(): boolean {
    return !!this.token && !!this.user();
  }

  login(email: string, password: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.baseUrl}/auth/login`, { email, password }).pipe(
      tap(res => {
        try {
          localStorage.setItem(TOKEN_KEY, res.access_token);
          localStorage.setItem(USER_KEY, JSON.stringify(res.user));
        } catch { /* storage unavailable: session lasts until reload */ }
        this.user.set(res.user);
      })
    );
  }

  register(name: string, email: string, password: string): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(`${this.baseUrl}/auth/register`, { name, email, password });
  }

  changePassword(current_password: string, new_password: string): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(`${this.baseUrl}/auth/change-password`, { current_password, new_password });
  }

  logout(redirect = true): void {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    } catch { /* ignore */ }
    this.user.set(null);
    if (redirect) this.router.navigate(['/login']);
  }

  // Admin: user management
  listUsers(status?: string): Observable<AuthUser[]> {
    const q = status ? `?status=${status}` : '';
    return this.http.get<AuthUser[]>(`${this.baseUrl}/users${q}`);
  }

  setUserStatus(id: number, action: 'approve' | 'reject' | 'disable'): Observable<AuthUser> {
    return this.http.post<AuthUser>(`${this.baseUrl}/users/${id}/${action}`, {});
  }

  setUserRole(id: number, role: 'user' | 'admin'): Observable<AuthUser> {
    return this.http.put<AuthUser>(`${this.baseUrl}/users/${id}/role`, { role });
  }

  private loadUser(): AuthUser | null {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  }
}
