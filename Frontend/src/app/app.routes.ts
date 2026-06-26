import { Routes } from '@angular/router';
import { DashboardComponent } from './components/dashboard/dashboard';
import { LogViewerComponent } from './components/log-viewer/log-viewer';
import { LogSourcesComponent } from './components/log-sources/log-sources';
import { RcaDashboardComponent } from './components/rca-dashboard/rca-dashboard';
import { IncidentQueueComponent } from './components/incident-queue/incident-queue';
import { GitlabDashboardComponent } from './components/gitlab-dashboard/gitlab-dashboard';
import { NotificationsComponent } from './components/notifications/notifications';

export const routes: Routes = [
  { path: 'dashboard', component: DashboardComponent },
  { path: 'logs', component: LogViewerComponent },
  { path: 'log-sources', component: LogSourcesComponent },
  { path: 'rca', component: RcaDashboardComponent },
  { path: 'incidents', component: IncidentQueueComponent },
  { path: 'gitlab-issues', component: GitlabDashboardComponent },
  { path: 'notifications', component: NotificationsComponent },
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: '**', redirectTo: 'dashboard' }
];
