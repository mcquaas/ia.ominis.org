'use strict';

/**
 * Custom routes for api-key
 */

module.exports = {
  routes: [
    {
      method: 'POST',
      path: '/api-keys/:id/revoke',
      handler: 'api-key.revoke',
      config: {
        policies: [],
        middlewares: [],
      },
    },
    {
      method: 'POST',
      path: '/api-keys/validate',
      handler: 'api-key.validate',
      config: {
        policies: [],
        middlewares: [],
        auth: false, // Public endpoint for API validation
      },
    },
    {
      method: 'GET',
      path: '/api-keys/:id/usage',
      handler: 'api-key.usage',
      config: {
        policies: [],
        middlewares: [],
      },
    },
  ],
};
