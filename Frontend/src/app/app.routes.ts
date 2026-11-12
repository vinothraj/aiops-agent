import { Routes } from '@angular/router';
import { DashboardComponent } from './components/dashboard/dashboard';
import { LogViewerComponent } from './components/log-viewer/log-viewer';
import { LogSourcesComponent } from './components/log-sources/log-sources';
import { RcaDashboardComponent } from './components/rca-dashboard/rca-dashboard';
import { IncidentQueueComponent } from './components/incident-queue/incident-queue';
import { IncidentGroupsComponent } from './components/incident-groups/incident-groups';
import { GitlabDashboardComponent } from './components/gitlab-dashboard/gitlab-dashboard';
import { NotificationsComponent } from './components/notifications/notifications';
import { SettingsComponent } from './components/settings/settings';
import { FixSessionsComponent } from './components/fix-sessions/fix-sessions';
import { LoginComponent } from './components/login/login';
import { UserManagementComponent } from './components/user-management/user-management';
import { authGuard, adminGuard } from './auth.guard';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  { path: 'users', component: UserManagementComponent, canActivate: [adminGuard] },
  { path: 'dashboard', component: DashboardComponent, canActivate: [authGuard] },
  { path: 'logs', component: LogViewerComponent, canActivate: [authGuard] },
  { path: 'log-sources', component: LogSourcesComponent, canActivate: [authGuard] },
  { path: 'rca', component: RcaDashboardComponent, canActivate: [authGuard] },
  { path: 'incidents', component: IncidentQueueComponent, canActivate: [authGuard] },
  { path: 'incident-groups', component: IncidentGroupsComponent, canActivate: [authGuard] },
  { path: 'gitlab-issues', component: GitlabDashboardComponent, canActivate: [authGuard] },
  { path: 'fix-sessions', component: FixSessionsComponent, canActivate: [authGuard] },
  { path: 'notifications', component: NotificationsComponent, canActivate: [authGuard] },
  { path: 'settings', component: SettingsComponent, canActivate: [authGuard] },
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: '**', redirectTo: 'dashboard' }
];
