'use strict';

/**
 * query-log service
 */

const { createCoreService } = require('@strapi/strapi').factories;

module.exports = createCoreService('api::query-log.query-log');
