import { setupServer } from 'msw/node'
import { handlers } from './handlers'

// Node MSW server shared across the suite. Per-test overrides via server.use().
export const server = setupServer(...handlers)
