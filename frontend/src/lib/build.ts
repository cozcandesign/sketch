// Arayüzün build bilgisi. vite.config.ts `define` ile gömer.
export const FRONTEND_GIT_SHA: string = typeof __GIT_SHA__ === 'string' ? __GIT_SHA__ : 'bilinmiyor'
export const FRONTEND_BUILD_TIME: string = typeof __BUILD_TIME__ === 'string' ? __BUILD_TIME__ : ''

/** İki commit de bilinip farklıysa uyarılır; "bilinmiyor" durumunda uyarı verilmez. */
export function isVersionMismatch(frontend: string, backend: string | undefined): boolean {
  if (!backend || backend === 'bilinmiyor' || frontend === 'bilinmiyor') return false
  return frontend !== backend
}
