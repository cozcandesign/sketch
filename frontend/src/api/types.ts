// Üretilen OpenAPI tiplerine kısa adlar. types.gen.ts elle düzenlenmez (`npm run gen-types`).
import type { components } from '@/api/types.gen'

export type HealthResponse = components['schemas']['HealthResponse']
export type CollectorHealth = components['schemas']['CollectorHealthOut']
export type HealthStatus = CollectorHealth['status']
