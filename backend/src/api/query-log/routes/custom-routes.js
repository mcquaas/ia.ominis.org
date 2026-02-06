'use strict';

/**
 * Custom routes for query-log
 */

module.exports = {
  routes: [
    {
      method: 'GET',
      path: '/query-logs/aggregated',
      handler: 'query-log.aggregated',
      config: {
        policies: [],
        middlewares: [],
      },
    },
  ],
};
