'use strict';

/**
 * query-log router
 */

const { createCoreRouter } = require('@strapi/strapi').factories;

module.exports = createCoreRouter('api::query-log.query-log');
