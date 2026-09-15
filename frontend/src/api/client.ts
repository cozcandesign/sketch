export const API_BASE = '/api/v1'

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} ${res.statusText}: ${await res.text()}`)
  }
  return (await res.json()) as T
}
