// Purpose: name the demo API client explicitly for the demo-mode dashboard.
// Responsibilities: re-export the /demo/* client so demo and tenant clients are clearly separated.
export { api as demoApi } from './api';
