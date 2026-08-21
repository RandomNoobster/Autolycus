/**
 * Game Data Types
 * 
 * TypeScript types for P&W game mechanics data (projects, policies).
 */

export interface Project {
  name: string;
  description: string;
}

export interface Policy {
  name: string;
  description: string;
}

export interface GameDataResponse {
  projects: Record<string, Project>;
  domesticPolicies: Record<string, Policy>;
}
