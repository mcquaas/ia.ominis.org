'use strict';

/**
 * Custom routes for system-stats
 */

module.exports = {
  routes: [
    {
      method: 'POST',
      path: '/system-stats/refresh',
      handler: 'system-stat.refresh',
      config: {
        policies: [],
        middlewares: [],
      },
    },
    {
      method: 'GET',
      path: '/system-stats/health',
      handler: 'system-stat.health',
      config: {
        policies: [],
        middlewares: [],
        auth: false, // Public health check
      },
    },
  ],
};
