import { RiskLevel } from '../types';

export function formatMw(val: number | null | undefined): string {
  if (val === null || val === undefined) return '--';
  return `${val.toFixed(1)} MW`;
}

export function formatMwInteger(val: number | null | undefined): string {
  if (val === null || val === undefined) return '--';
  return `${Math.round(val)} MW`;
}

export function formatTto(min: number | null): string {
  if (min === null) return 'Safe (Nominal)';
  return `${min} min`;
}

export function getRiskColorClass(level: RiskLevel): {
  bg: string;
  text: string;
  border: string;
  dot: string;
} {
  switch (level) {
    case 'CRITICAL':
      return {
        bg: 'bg-red-50',
        text: 'text-red-700',
        border: 'border-red-200',
        dot: 'bg-red-600',
      };
    case 'HIGH':
      return {
        bg: 'bg-amber-50',
        text: 'text-amber-800',
        border: 'border-amber-200',
        dot: 'bg-amber-500',
      };
    case 'MODERATE':
      return {
        bg: 'bg-blue-50',
        text: 'text-blue-700',
        border: 'border-blue-200',
        dot: 'bg-blue-500',
      };
    case 'LOW':
    default:
      return {
        bg: 'bg-emerald-50',
        text: 'text-emerald-700',
        border: 'border-emerald-200',
        dot: 'bg-emerald-500',
      };
  }
}

export function getStressScoreColor(score: number): string {
  if (score >= 85) return 'text-red-600';
  if (score >= 65) return 'text-amber-600';
  if (score >= 40) return 'text-blue-600';
  return 'text-emerald-600';
}
