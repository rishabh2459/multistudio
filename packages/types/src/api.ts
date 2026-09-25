// Types of the local HTTP API (apps/api), generated from schemas/openapi.json by
// `make schemas`. Use the Schema helper: Schema<'ProjectOut'>, Schema<'JobOut'>, ...
import type { components, paths } from './generated/api';

export type { components, paths };
export type Schema<Name extends keyof components['schemas']> = components['schemas'][Name];
