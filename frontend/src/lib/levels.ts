/**
 * Developer level definitions.
 *
 * Labels and thresholds must match the backend's roadmap service so the rail
 * and the XP readout agree.
 */

export interface DeveloperLevel {
  id: string;
  label: string;
  xp: number;
}

export const LEVEL_ORDER: readonly DeveloperLevel[] = [
  { id: "junior", label: "Junior", xp: 0 },
  { id: "intermediate", label: "Intermediate", xp: 1000 },
  { id: "senior", label: "Senior", xp: 3000 },
  { id: "staff", label: "Staff", xp: 7000 },
  { id: "principal", label: "Principal", xp: 15000 },
];
