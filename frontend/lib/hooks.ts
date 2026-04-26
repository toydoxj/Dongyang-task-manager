// SWR 기반 도메인 훅. 키를 한 곳에서 관리해 캐시 일관성을 유지한다.

import useSWR, { type SWRResponse } from "swr";

import {
  getCashflow,
  getProject,
  listClients,
  listProjects,
  listTasks,
} from "./api";
import type {
  CashflowResponse,
  ClientListResponse,
  Project,
  ProjectListResponse,
  TaskListResponse,
} from "./domain";

// 키 헬퍼 — 디버깅/캐시 무효화 시 일관성 위해
export const keys = {
  projects: (filters?: Parameters<typeof listProjects>[0]) =>
    ["projects", filters ?? null] as const,
  project: (id: string) => ["project", id] as const,
  tasks: (filters?: Parameters<typeof listTasks>[0]) =>
    ["tasks", filters ?? null] as const,
  cashflow: (filters?: Parameters<typeof getCashflow>[0]) =>
    ["cashflow", filters ?? null] as const,
  clients: () => ["clients"] as const,
};

export function useProjects(
  filters?: Parameters<typeof listProjects>[0],
  enabled: boolean = true,
): SWRResponse<ProjectListResponse> {
  return useSWR(
    enabled ? keys.projects(filters) : null,
    () => listProjects(filters),
  );
}

export function useProject(id: string | null): SWRResponse<Project> {
  return useSWR(id ? keys.project(id) : null, () => getProject(id!));
}

export function useTasks(
  filters?: Parameters<typeof listTasks>[0],
): SWRResponse<TaskListResponse> {
  return useSWR(keys.tasks(filters), () => listTasks(filters));
}

export function useCashflow(
  filters?: Parameters<typeof getCashflow>[0],
): SWRResponse<CashflowResponse> {
  return useSWR(keys.cashflow(filters), () => getCashflow(filters));
}

export function useClients(
  enabled: boolean = true,
): SWRResponse<ClientListResponse> {
  return useSWR(enabled ? keys.clients() : null, () => listClients());
}
